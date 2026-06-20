import os

from src.file_explorer import FileExplorer


class _FakeParent:
    def __init__(self):
        self.calls = []
        self.cancelled = []

    def after(self, delay_ms, callback):
        self.calls.append((delay_ms, callback))
        return f"job-{len(self.calls)}"

    def after_cancel(self, job_id):
        self.cancelled.append(job_id)


class _FakeTree:
    def __init__(self):
        self.nodes = {
            "folder": {
                "values": ("C:/project/folder",),
                "open": True,
                "children": ["file"],
            },
            "file": {
                "values": ("C:/project/folder/file.py",),
                "open": False,
                "children": [],
            },
        }
        self.selected = ("file",)
        self.reselected = None

    def selection(self):
        return self.selected

    def selection_set(self, item_id):
        self.reselected = item_id

    def get_children(self, parent=""):
        if parent == "":
            return ["folder"]
        return list(self.nodes[parent]["children"])

    def item(self, item_id, option=None, **kwargs):
        node = self.nodes[item_id]
        if kwargs:
            if "open" in kwargs:
                node["open"] = kwargs["open"]
            return None
        if option == "values":
            return node["values"]
        if option == "open":
            return node["open"]
        return node


def _build_explorer():
    explorer = object.__new__(FileExplorer)
    explorer.parent = _FakeParent()
    explorer.tree = _FakeTree()
    explorer.current_folder = None
    explorer._auto_refresh_job = None
    explorer._folder_signature = None
    explorer._auto_refresh_interval_ms = 1000
    return explorer


class TestFileExplorerAutoRefresh:
    def test_build_folder_signature_changes_when_file_changes(self, tmp_path):
        explorer = _build_explorer()
        file_path = tmp_path / "main.py"
        file_path.write_text("print('a')\n", encoding="utf-8")

        first_signature = explorer._build_folder_signature(str(tmp_path))
        file_path.write_text("print('b')\n", encoding="utf-8")
        second_signature = explorer._build_folder_signature(str(tmp_path))

        assert first_signature != second_signature

    def test_auto_refresh_tick_refreshes_when_signature_changes(self, tmp_path):
        explorer = _build_explorer()
        explorer.current_folder = str(tmp_path)
        explorer._folder_signature = (("main.py", False, 1, 10),)
        explorer.refresh_called = False

        def refresh():
            explorer.refresh_called = True

        explorer.refresh = refresh
        (tmp_path / "main.py").write_text("print('hola')\n", encoding="utf-8")

        explorer._auto_refresh_tick()

        assert explorer.refresh_called is True

    def test_capture_and_restore_tree_state_preserves_expansion_and_selection(self):
        explorer = _build_explorer()

        tree_state = explorer._capture_tree_state()
        explorer.tree.nodes["folder"]["open"] = False
        explorer.tree.selected = ()

        explorer._restore_tree_state(tree_state)

        assert explorer.tree.nodes["folder"]["open"] is True
        assert explorer.tree.reselected == "file"