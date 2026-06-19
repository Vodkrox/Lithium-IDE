"""
Tests for src/ai_powered/conversation_manager.py.
"""

import json
import os
from datetime import datetime

import pytest

from src.ai_powered.conversation_manager import (
    Conversation,
    ConversationManager,
    get_conversation_manager,
    reset_conversation_manager,
)

# =========================================================================
# Conversation model
# =========================================================================


class TestConversation:
    def test_create_with_defaults(self):
        conv = Conversation()
        assert conv.title == "New Conversation"
        assert conv.messages == []
        assert isinstance(conv.id, str)
        assert len(conv.id) > 0

    def test_create_with_custom_id(self):
        conv = Conversation(conversation_id="my-id")
        assert conv.id == "my-id"

    def test_add_message(self):
        conv = Conversation()
        conv.add_message("user", "Hello")
        assert len(conv.messages) == 1
        assert conv.messages[0]["role"] == "user"
        assert conv.messages[0]["content"] == "Hello"

    def test_add_message_updates_updated_at(self):
        conv = Conversation()
        old = conv.updated_at
        conv.add_message("user", "test")
        assert conv.updated_at >= old

    def test_first_user_message_sets_title(self):
        conv = Conversation()
        conv.add_message("user", "How do I sort a list in Python?")
        assert "How do I sort" in conv.title

    def test_first_user_message_truncates_long_title(self):
        conv = Conversation()
        long_msg = "a" * 100
        conv.add_message("user", long_msg)
        assert len(conv.title) <= 53  # 50 + "..."

    def test_assistant_message_does_not_change_title(self):
        conv = Conversation(title="Custom Title")
        conv.add_message("assistant", "Here is the answer")
        assert conv.title == "Custom Title"

    def test_add_message_with_metadata(self):
        conv = Conversation()
        conv.add_message("user", "hi", metadata={"source": "chat"})
        assert conv.messages[0]["metadata"]["source"] == "chat"

    def test_add_message_default_metadata_is_empty(self):
        conv = Conversation()
        conv.add_message("user", "hi")
        assert conv.messages[0]["metadata"] == {}

    def test_to_dict_includes_all_fields(self):
        conv = Conversation(conversation_id="abc", title="Test")
        # Add an assistant message first so it doesn't overwrite the title
        conv.add_message("assistant", "welcome")
        d = conv.to_dict()
        assert d["id"] == "abc"
        assert d["title"] == "Test"
        assert len(d["messages"]) == 1
        assert "created_at" in d
        assert "updated_at" in d

    def test_from_dict_restores_conversation(self):
        original = Conversation(title="Restored")
        original.add_message("user", "hi")
        d = original.to_dict()
        restored = Conversation.from_dict(d)
        assert restored.id == original.id
        assert restored.title == original.title
        assert len(restored.messages) == 1
        assert restored.messages[0]["content"] == "hi"

    def test_str_representation(self):
        conv = Conversation(conversation_id="id123", title="My Chat")
        # Add an assistant message first so it doesn't overwrite the title
        conv.add_message("assistant", "hello")
        s = str(conv)
        assert "id123" in s
        assert "My Chat" in s
        assert "1 messages" in s

    def test_empty_messages_str(self):
        conv = Conversation(conversation_id="empty", title="Empty")
        s = str(conv)
        assert "0 messages" in s


# =========================================================================
# ConversationManager
# =========================================================================


@pytest.fixture
def manager(tmp_path):
    """Create a ConversationManager that writes to a temp directory."""
    m = ConversationManager(storage_path=str(tmp_path))
    reset_conversation_manager()  # Clean global state
    return m


class TestConversationManager:
    def test_create_manager_creates_storage(self, tmp_path):
        mgr = ConversationManager(storage_path=str(tmp_path))
        assert os.path.exists(str(tmp_path))

    def test_default_storage_path_is_absolute(self):
        mgr = ConversationManager()
        assert os.path.isabs(mgr.storage_path)

    def test_create_conversation(self, manager):
        conv = manager.create_conversation("My Chat")
        assert conv.title == "My Chat"
        assert manager.current_conversation is conv

    def test_create_conversation_saves_to_disk(self, manager):
        conv = manager.create_conversation("Saved")
        path = os.path.join(manager.storage_path, f"{conv.id}.json")
        assert os.path.exists(path)

    def test_save_and_load_conversation(self, manager):
        conv = manager.create_conversation("Test")
        # Add an assistant message first so it doesn't overwrite the title
        conv.add_message("assistant", "welcome")
        conv.add_message("user", "hello")
        assert conv.title == "Test"  # Title unchanged
        manager.save_conversation(conv)

        # Load into a new manager
        manager2 = ConversationManager(storage_path=manager.storage_path)
        loaded = manager2.load_conversation(conv.id)
        assert loaded is not None
        assert loaded.title == "Test"
        assert len(loaded.messages) == 2
        assert loaded.messages[1]["content"] == "hello"

    def test_load_nonexistent_returns_none(self, manager):
        result = manager.load_conversation("nonexistent-id")
        assert result is None

    def test_delete_conversation(self, manager):
        conv = manager.create_conversation("Delete Me")
        assert manager.delete_conversation(conv.id) is True
        path = os.path.join(manager.storage_path, f"{conv.id}.json")
        assert not os.path.exists(path)

    def test_delete_nonexistent_returns_true(self, manager):
        """Deleting a non-existent conversation should return True (no-op)."""
        assert manager.delete_conversation("ghost") is True

    def test_delete_clears_current(self, manager):
        conv = manager.create_conversation("Current")
        manager.delete_conversation(conv.id)
        assert manager.current_conversation is None

    def test_list_conversations(self, manager):
        c1 = manager.create_conversation("First")
        c2 = manager.create_conversation("Second")
        convs = manager.list_conversations()
        assert len(convs) == 2
        titles = [c["title"] for c in convs]
        assert "First" in titles
        assert "Second" in titles

    def test_list_conversations_sorted_by_updated_at(self, manager):
        c1 = manager.create_conversation("Older")
        c2 = manager.create_conversation("Newer")
        convs = manager.list_conversations()
        assert convs[0]["title"] == "Newer"  # Most recent first

    def test_get_conversation_messages(self, manager):
        conv = manager.create_conversation("Messages")
        conv.add_message("user", "msg1")
        conv.add_message("assistant", "msg2")
        manager.save_conversation(conv)
        messages = manager.get_conversation_messages(conv.id)
        assert len(messages) == 2
        assert messages[0]["content"] == "msg1"

    def test_get_conversation_messages_nonexistent(self, manager):
        assert manager.get_conversation_messages("ghost") == []

    def test_rename_conversation(self, manager):
        conv = manager.create_conversation("Old Name")
        assert manager.rename_conversation(conv.id, "New Name") is True
        loaded = manager.load_conversation(conv.id)
        assert loaded.title == "New Name"

    def test_rename_nonexistent_returns_false(self, manager):
        assert manager.rename_conversation("ghost", "New Name") is False

    def test_get_current_conversation(self, manager):
        assert manager.get_current_conversation() is None
        conv = manager.create_conversation("Current")
        assert manager.get_current_conversation() is conv

    def test_set_current_conversation(self, manager):
        conv = Conversation(title="Manual Set")
        manager.set_current_conversation(conv)
        assert manager.get_current_conversation() is conv

    def test_clear_current_conversation(self, manager):
        manager.create_conversation("Temp")
        manager.clear_current_conversation()
        assert manager.get_current_conversation() is None

    def test_save_nonexistent_conversation_returns_false(self, manager):
        assert manager.save_conversation(None) is False


class TestConversationExport:
    def _setup_without_overwriting_title(self, manager, title):
        """Create a conversation and add a user message without overwriting the title."""
        conv = manager.create_conversation(title)
        # Add an assistant message first so the user message doesn't overwrite the title
        conv.add_message("assistant", "I will help")
        conv.add_message("user", "hello")
        assert conv.title == title  # Title should be preserved
        manager.save_conversation(conv)
        return conv

    def test_export_txt(self, manager):
        conv = self._setup_without_overwriting_title(manager, "Export")
        result = manager.export_conversation(conv.id, "txt")
        assert result is not None
        assert "Export" in result
        assert "hello" in result
        assert "[USER]" in result

    def test_export_json(self, manager):
        conv = self._setup_without_overwriting_title(manager, "Export JSON")
        result = manager.export_conversation(conv.id, "json")
        assert result is not None
        data = json.loads(result)
        assert data["title"] == "Export JSON"

    def test_export_md(self, manager):
        conv = self._setup_without_overwriting_title(manager, "Export MD")
        result = manager.export_conversation(conv.id, "md")
        assert result is not None
        assert "# Export MD" in result
        assert "USER" in result

    def test_export_invalid_format_returns_none(self, manager):
        conv = manager.create_conversation("Invalid")
        result = manager.export_conversation(conv.id, "pdf")
        assert result is None

    def test_export_nonexistent_returns_none(self, manager):
        assert manager.export_conversation("ghost", "txt") is None


# =========================================================================
# Global manager helpers
# =========================================================================


class TestGlobalManager:
    def test_get_conversation_manager_singleton(self):
        reset_conversation_manager()
        m1 = get_conversation_manager()
        m2 = get_conversation_manager()
        assert m1 is m2

    def test_reset_conversation_manager(self):
        reset_conversation_manager()
        m1 = get_conversation_manager()
        reset_conversation_manager()
        m2 = get_conversation_manager()
        assert m1 is not m2
