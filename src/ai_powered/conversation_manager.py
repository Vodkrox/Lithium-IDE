"""
Conversation Manager module for Lithium IDE.
Provides conversation history management for AI chat sessions.
"""

import os
import sys
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any


class Conversation:
    """Represents a single conversation with the AI."""

    def __init__(self, conversation_id: str = None, title: str = "New Conversation",
                 messages: List[Dict] = None, created_at: str = None, updated_at: str = None):
        self.id = conversation_id or str(uuid.uuid4())
        self.title = title
        self.messages = messages or []
        self.created_at = created_at or datetime.now().isoformat()
        self.updated_at = updated_at or datetime.now().isoformat()

    def add_message(self, role: str, content: str, metadata: Dict = None):
        """Add a message to the conversation."""
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        self.messages.append(message)
        self.updated_at = datetime.now().isoformat()

        if len(self.messages) == 1 and role == "user":
            self.title = content[:50] + ("..." if len(content) > 50 else "")

    def to_dict(self) -> Dict:
        """Convert conversation to dictionary for serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "messages": self.messages,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Conversation':
        """Create a Conversation from a dictionary."""
        return cls(
            conversation_id=data.get("id"),
            title=data.get("title", "New Conversation"),
            messages=data.get("messages", []),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at")
        )

    def __str__(self):
        return f"Conversation({self.id}): {self.title} ({len(self.messages)} messages)"


class ConversationManager:
    """Manages conversation history for AI chat sessions."""

    def __init__(self, storage_path: str = None):
        """
        Initialize the Conversation Manager.

        Args:
            storage_path: Directory path to store conversation files
        """
        if storage_path is None:
            storage_path = self._get_default_storage_path()
        self.storage_path = storage_path
        self.current_conversation: Optional[Conversation] = None
        self._ensure_storage_exists()

    @staticmethod
    def _get_default_storage_path():
        """Return the default conversations directory inside appdata."""
        if sys.platform == "win32":
            base = os.getenv("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
        elif sys.platform == "darwin":
            base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
        else:
            base = os.getenv("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
        return os.path.join(base, "LithiumIDE", "conversations")

    def _ensure_storage_exists(self):
        """Create storage directory if it doesn't exist."""
        os.makedirs(self.storage_path, exist_ok=True)

    def _get_conversation_path(self, conversation_id: str) -> str:
        """Get the file path for a conversation."""
        return os.path.join(self.storage_path, f"{conversation_id}.json")

    def save_conversation(self, conversation: Conversation = None) -> bool:
        """
        Save a conversation to disk.

        Args:
            conversation: Conversation to save, or current if None

        Returns:
            True if saved successfully
        """
        if conversation is None:
            conversation = self.current_conversation

        if conversation is None:
            return False

        try:
            path = self._get_conversation_path(conversation.id)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(conversation.to_dict(), f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error saving conversation: {e}")
            return False

    def load_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """
        Load a conversation from disk.

        Args:
            conversation_id: ID of the conversation to load

        Returns:
            Loaded Conversation or None if not found
        """
        try:
            path = self._get_conversation_path(conversation_id)
            if not os.path.exists(path):
                return None

            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            conversation = Conversation.from_dict(data)
            self.current_conversation = conversation
            return conversation
        except Exception as e:
            print(f"Error loading conversation: {e}")
            return None

    def create_conversation(self, title: str = "New Conversation") -> Conversation:
        """
        Create a new conversation.

        Args:
            title: Optional title for the conversation

        Returns:
            The newly created Conversation
        """
        conversation = Conversation(title=title)
        self.current_conversation = conversation
        self.save_conversation(conversation)
        return conversation

    def delete_conversation(self, conversation_id: str) -> bool:
        """
        Delete a conversation.

        Args:
            conversation_id: ID of the conversation to delete

        Returns:
            True if deleted successfully
        """
        try:
            path = self._get_conversation_path(conversation_id)
            if os.path.exists(path):
                os.remove(path)

            if self.current_conversation and self.current_conversation.id == conversation_id:
                self.current_conversation = None

            return True
        except Exception as e:
            print(f"Error deleting conversation: {e}")
            return False

    def list_conversations(self) -> List[Dict]:
        """
        List all saved conversations with summary info.

        Returns:
            List of conversation summaries (id, title, message_count, updated_at)
        """
        conversations = []

        try:
            for filename in os.listdir(self.storage_path):
                if filename.endswith('.json'):
                    path = os.path.join(self.storage_path, filename)
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            data = json.load(f)

                        conversations.append({
                            "id": data.get("id", filename[:-5]),
                            "title": data.get("title", "Untitled"),
                            "message_count": len(data.get("messages", [])),
                            "updated_at": data.get("updated_at", ""),
                            "created_at": data.get("created_at", "")
                        })
                    except Exception:
                        continue
        except Exception:
            pass

        conversations.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return conversations

    def get_conversation_messages(self, conversation_id: str) -> List[Dict]:
        """
        Get all messages from a conversation.

        Args:
            conversation_id: ID of the conversation

        Returns:
            List of messages
        """
        conversation = self.load_conversation(conversation_id)
        if conversation:
            return conversation.messages
        return []

    def rename_conversation(self, conversation_id: str, new_title: str) -> bool:
        """
        Rename a conversation.

        Args:
            conversation_id: ID of the conversation
            new_title: New title for the conversation

        Returns:
            True if renamed successfully
        """
        conversation = self.load_conversation(conversation_id)
        if conversation:
            conversation.title = new_title
            return self.save_conversation(conversation)
        return False

    def get_current_conversation(self) -> Optional[Conversation]:
        """Get the current active conversation."""
        return self.current_conversation

    def set_current_conversation(self, conversation: Conversation):
        """Set the current active conversation."""
        self.current_conversation = conversation

    def clear_current_conversation(self):
        """Clear the current conversation reference."""
        self.current_conversation = None

    def export_conversation(self, conversation_id: str, format: str = "txt") -> Optional[str]:
        """
        Export a conversation to a string.

        Args:
            conversation_id: ID of the conversation to export
            format: Export format ("txt", "json", "md")

        Returns:
            Exported conversation as string
        """
        conversation = self.load_conversation(conversation_id)
        if not conversation:
            return None

        if format == "json":
            return json.dumps(conversation.to_dict(), indent=2, ensure_ascii=False)

        elif format == "md":
            lines = [f"# {conversation.title}\n"]
            for msg in conversation.messages:
                role = msg.get("role", "unknown").upper()
                content = msg.get("content", "")
                lines.append(f"## {role}\n\n{content}\n")
            return "\n".join(lines)

        elif format == "txt":
            lines = [f"Conversation: {conversation.title}\n", "=" * 50]
            for msg in conversation.messages:
                role = msg.get("role", "unknown").upper()
                content = msg.get("content", "")
                lines.append(f"\n[{role}]\n{content}")
            return "\n".join(lines)

        return None


_default_manager = None


def get_conversation_manager(storage_path: str = None) -> ConversationManager:
    """
    Get or create the default Conversation Manager.

    Args:
        storage_path: Optional custom storage path

    Returns:
        ConversationManager instance
    """
    global _default_manager

    if _default_manager is None:
        _default_manager = ConversationManager(storage_path)

    return _default_manager


def reset_conversation_manager():
    """Reset the default manager (useful for testing)."""
    global _default_manager
    _default_manager = None
