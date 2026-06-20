import os
from unittest.mock import MagicMock, patch

from src.editor import LithiumEditorController


def _build_controller(tmp_path):
    editor = MagicMock()
    editor.get.return_value = "print('hola')\n"
    settings_manager = MagicMock()

    controller = LithiumEditorController(
        root=MagicMock(),
        editor=editor,
        line_numbers=MagicMock(),
        status_bar=MagicMock(),
        selected_lang=MagicMock(get=MagicMock(return_value="Python")),
        editor_label=MagicMock(),
        settings_manager=settings_manager,
    )
    controller.update_status = MagicMock()
    controller.update_line_numbers = MagicMock()
    controller.mark_clean = MagicMock()
    controller.file_path = os.path.join(tmp_path, "sample.py")
    controller.on_filesystem_change_callback = MagicMock()
    return controller


class TestEditorFilesystemNotifications:
    def test_save_file_notifies_filesystem_change(self, tmp_path):
        controller = _build_controller(tmp_path)

        result = controller.save_file()

        assert result is True
        controller.on_filesystem_change_callback.assert_called_once_with()

    def test_save_as_file_notifies_filesystem_change(self, tmp_path):
        controller = _build_controller(tmp_path)
        controller.file_path = None
        save_path = os.path.join(tmp_path, "new_file.py")

        with patch("src.editor.filedialog.asksaveasfilename", return_value=save_path):
            result = controller.save_as_file()

        assert result is True
        assert controller.file_path == save_path
        controller.on_filesystem_change_callback.assert_called_once_with()