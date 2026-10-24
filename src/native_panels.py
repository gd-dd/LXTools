"""Tool-owned QWidget panels. Trusted native code, explicitly NOT a sandbox."""
import importlib.abc
import importlib.util
import json
import re
import sys
import types
import uuid
from pathlib import Path
from PySide6.QtWidgets import QWidget
from library import write_json
from lx_protocol import safe_path, checked_bytes, validate_panel


class PanelContext:
    api_version = 1

    def __init__(self, tool, config_root):
        self.identity = tool['id']
        if not re.fullmatch(r'repo-[0-9]+', self.identity):
            raise ValueError('工具身份无效')
        self.version = tool['version']
        self.package_root = Path(tool['root']).resolve()
        self.data_root = Path(config_root).resolve() / 'tool-data' / self.identity
        self.data_root.mkdir(parents=True, exist_ok=True)
        self._files = dict(tool['files'])

    def resource(self, relative_path):
        safe_path(relative_path)
        if relative_path not in self._files:
            raise ValueError('资源未列入 files：' + relative_path)
        path = (self.package_root / relative_path).resolve()
        if not path.is_relative_to(self.package_root):
            raise ValueError('工具资源越界')
        checked_bytes(path.read_bytes(), self._files[relative_path])
        return path

    def load_settings(self):
        path = self.data_root / 'panel-settings.json'
        settings = json.loads(path.read_text('utf-8')) if path.exists() else {}
        if not isinstance(settings, dict):
            raise ValueError('工具配置必须为 JSON 对象')
        return settings

    def save_settings(self, settings):
        if not isinstance(settings, dict):
            raise ValueError('工具配置必须为 JSON 对象')
        write_json(self.data_root / 'panel-settings.json', settings)


class _Loader(importlib.abc.Loader):
    def __init__(self, context, relative):
        self.context, self.relative = context, relative

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        path = self.context.resource(self.relative)
        module.__file__ = str(path)
        # Never produce bytecode in immutable, hash-checked tool packages.
        exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)


class _Finder(importlib.abc.MetaPathFinder):
    def __init__(self, namespace, context, directory):
        self.namespace, self.context, self.directory = namespace, context, directory

    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith(self.namespace + '.'):
            return None
        name = fullname[len(self.namespace)+1:].replace('.', '/')
        base = (self.directory / name).as_posix()
        for relative, package in ((base+'.py', False), (base+'/__init__.py', True)):
            if relative in self.context._files:
                return importlib.util.spec_from_loader(fullname, _Loader(self.context, relative), is_package=package)
        raise ModuleNotFoundError('工具模块未声明：' + fullname)


class NativePanelHandle:
    def __init__(self, tool, config_root, parent):
        spec = validate_panel(tool['panelData'], tool)
        self.widget = None
        self.namespace = '_lx_panel_' + uuid.uuid4().hex
        self.context = PanelContext(tool, config_root)
        self.finder = _Finder(self.namespace, self.context, Path(spec['entry']).parent)
        # Validate the entire package before any tool-owned Python executes.
        for relative in self.context._files:
            self.context.resource(relative)
        package = types.ModuleType(self.namespace)
        package.__path__ = []
        sys.modules[self.namespace] = package
        sys.meta_path.insert(0, self.finder)
        try:
            module_spec = importlib.util.spec_from_loader(self.namespace+'.__entry__', _Loader(self.context, spec['entry']))
            module = importlib.util.module_from_spec(module_spec)
            sys.modules[module_spec.name] = module
            module_spec.loader.exec_module(module)
            widget = module.create_panel(self.context, parent)
            if not isinstance(widget, QWidget):
                raise TypeError('create_panel 必须返回 QWidget')
            self.widget = widget
            if widget.parentWidget() is not parent or not callable(getattr(widget, 'shutdown', None)):
                raise TypeError('面板必须使用传入的 parent 并实现 shutdown()')
        except BaseException:
            self.shutdown()
            raise

    def shutdown(self):
        widget, self.widget = self.widget, None
        error = None
        if widget is not None:
            try:
                callback = getattr(widget, 'shutdown', None)
                if callable(callback):callback()
            except Exception as exc:
                error = str(exc)
            finally:
                widget.hide()
                widget.deleteLater()
        if self.finder in sys.meta_path:
            sys.meta_path.remove(self.finder)
        for name in list(sys.modules):
            if name == self.namespace or name.startswith(self.namespace+'.'):
                del sys.modules[name]
        return error
