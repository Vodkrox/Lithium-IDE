"""
Conversation Manager module for Lithium IDE.
Provides conversation history management for AI chat sessions.
"""

import json
import os
import sys
import uuid
from datetime import datetime
from typing import Dict, List, Optional


class Conversation:
    """Represents a single conversation with the AI."""

    def __init__(
        self,
        conversation_id: str = None,
        title: str = "New Conversation",
        messages: List[Dict] = None,
        created_at: str = None,
        updated_at: str = None,
    ):
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
            "metadata": metadata or {},
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
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Conversation":
        """Create a Conversation from a dictionary."""
        return cls(
            conversation_id=data.get("id"),
            title=data.get("title", "New Conversation"),
            messages=data.get("messages", []),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
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
            base = os.path.join(
                os.path.expanduser("~"), "Library", "Application Support"
            )
        else:
            base = os.getenv("XDG_CONFIG_HOME") or os.path.join(
                os.path.expanduser("~"), ".config"
            )
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
            with open(path, "w", encoding="utf-8") as f:
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

            with open(path, "r", encoding="utf-8") as f:
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

            if (
                self.current_conversation
                and self.current_conversation.id == conversation_id
            ):
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
                if filename.endswith(".json"):
                    path = os.path.join(self.storage_path, filename)
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            data = json.load(f)

                        conversations.append(
                            {
                                "id": data.get("id", filename[:-5]),
                                "title": data.get("title", "Untitled"),
                                "message_count": len(data.get("messages", [])),
                                "updated_at": data.get("updated_at", ""),
                                "created_at": data.get("created_at", ""),
                            }
                        )
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

    # ------------------------------------------------------------------
    # Context window management
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token estimation: ~4 characters per token."""
        return len(text) // 4

    def get_context_window(
        self, messages: List[Dict], max_tokens: int = 4096
    ) -> List[Dict]:
        """
        Return only the most recent messages that fit within the token limit,
        preserving the system prompt (if present as the first message).

        Uses a rough estimation of ~4 chars per token.

        Args:
            messages: Full list of message dicts (each with "role" and "content").
            max_tokens: Maximum allowed tokens in the returned window.

        Returns:
            Truncated list of messages fitting within the budget.
        """
        if not messages:
            return []

        budget = max_tokens
        result = []

        # Always keep the system prompt (first message with role "system")
        system_prompt = None
        remaining = list(messages)
        if remaining and remaining[0].get("role") == "system":
            system_prompt = remaining.pop(0)

        if system_prompt:
            sys_tokens = self._estimate_tokens(system_prompt.get("content", ""))
            if sys_tokens <= budget:
                result.append(system_prompt)
                budget -= sys_tokens
            # if the system prompt alone exceeds budget we still include it trimmed
            else:
                truncated = system_prompt.get("content", "")[: max_tokens * 4]
                result.append({"role": "system", "content": truncated})
                budget = 0

        # Walk from the newest message backward, collecting from the end
        selected = []
        for msg in reversed(remaining):
            tokens = self._estimate_tokens(msg.get("content", ""))
            if tokens <= budget:
                selected.append(msg)
                budget -= tokens
            else:
                # Partially include the message if we have some budget left
                if budget > 0:
                    truncated = msg.get("content", "")[: budget * 4]
                    selected.append({**msg, "content": truncated})
                break

        result.extend(reversed(selected))
        return result

    # ------------------------------------------------------------------
    # Summarization
    # ------------------------------------------------------------------

    @staticmethod
    def _role_distribution(messages: List[Dict]) -> str:
        """Return a short description of role distribution."""
        counts: Dict[str, int] = {}
        for m in messages:
            role = m.get("role", "unknown")
            counts[role] = counts.get(role, 0) + 1
        return ", ".join(f"{k}: {v}" for k, v in counts.items())

    def summarize_old_messages(
        self, messages: List[Dict], max_messages: int = 10
    ) -> str:
        """
        Summarize older messages (beyond max_messages) into a short paragraph
        when the conversation has grown too long. Returns an empty string if
        there are fewer messages than max_messages.

        Args:
            messages: Full list of message dicts.
            max_messages: Maximum number of recent messages to keep unsorted.

        Returns:
            A short summary string of the older messages, or empty string.
        """
        if len(messages) <= max_messages:
            return ""

        old = messages[:-max_messages]
        total_chars = sum(len(m.get("content", "")) for m in old)
        role_summary = self._role_distribution(old)

        # Extract key topics from old user messages
        user_topics = []
        for m in old:
            if m.get("role") == "user":
                content = m.get("content", "")
                # Grab first meaningful line or truncated content
                first_line = content.split("\n")[0][:80].strip()
                if first_line:
                    user_topics.append(first_line)
                if len(user_topics) >= 3:
                    break

        summary = (
            f"[Earlier conversation summary — {len(old)} older messages, "
            f"{total_chars} characters, roles: {role_summary}]"
        )
        if user_topics:
            topics = "; ".join(user_topics)
            summary += f"\nKey user topics: {topics}"

        return summary

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_conversations(self, query: str) -> List[Dict]:
        """
        Search for text across all saved conversations.

        Args:
            query: Text to search for (case-insensitive).

        Returns:
            List of dicts with conversation_id, title, snippet, and matched_message index.
        """
        results = []
        query_lower = query.lower()

        for filename in os.listdir(self.storage_path):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(self.storage_path, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue

            conv_id = data.get("id", filename[:-5])
            title = data.get("title", "Untitled")
            messages = data.get("messages", [])

            for idx, msg in enumerate(messages):
                content = msg.get("content", "")
                if query_lower in content.lower():
                    # Build a short snippet around the match
                    pos = content.lower().find(query_lower)
                    start = max(0, pos - 60)
                    end = min(len(content), pos + len(query) + 60)
                    snippet = (
                        ("…" if start > 0 else "")
                        + content[start:end]
                        + ("…" if end < len(content) else "")
                    )
                    results.append(
                        {
                            "conversation_id": conv_id,
                            "title": title,
                            "role": msg.get("role", "unknown"),
                            "timestamp": msg.get("timestamp", ""),
                            "snippet": snippet,
                            "matched_message": idx,
                        }
                    )
        return results

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_conversation_stats(self, conversation_id: str) -> Optional[Dict]:
        """
        Return statistics about a conversation.

        Returns:
            Dict with message_count, duration_seconds, roles, first_message,
            last_message, average_message_length, or None if not found.
        """
        conversation = self.load_conversation(conversation_id)
        if not conversation:
            return None

        messages = conversation.messages
        if not messages:
            return {
                "message_count": 0,
                "duration_seconds": 0,
                "roles": {},
                "first_message": None,
                "last_message": None,
                "average_message_length": 0,
            }

        timestamps = []
        role_counts: Dict[str, int] = {}
        total_length = 0

        for msg in messages:
            role = msg.get("role", "unknown")
            role_counts[role] = role_counts.get(role, 0) + 1
            total_length += len(msg.get("content", ""))

            ts = msg.get("timestamp")
            if ts:
                try:
                    timestamps.append(datetime.fromisoformat(ts))
                except (ValueError, TypeError):
                    pass

        duration = 0
        if len(timestamps) >= 2:
            duration = (max(timestamps) - min(timestamps)).total_seconds()

        first_msg = messages[0] if messages else None
        last_msg = messages[-1] if messages else None

        return {
            "message_count": len(messages),
            "duration_seconds": duration,
            "roles": role_counts,
            "first_message": first_msg,
            "last_message": last_msg,
            "average_message_length": total_length // len(messages) if messages else 0,
        }

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    def merge_conversations(
        self, conversation_ids: List[str], new_title: str
    ) -> Optional[Conversation]:
        """
        Merge multiple conversations into one, preserving message order by timestamp.

        Args:
            conversation_ids: List of conversation IDs to merge.
            new_title: Title for the new merged conversation.

        Returns:
            The new merged Conversation, or None if no valid conversations found.
        """
        all_messages = []
        merged_created = None

        for cid in conversation_ids:
            conv = self.load_conversation(cid)
            if conv is None:
                continue
            for msg in conv.messages:
                # Tag each message with its source conversation id
                tagged = dict(msg)
                tagged["metadata"] = dict(tagged.get("metadata", {}))
                tagged["metadata"]["source_conversation"] = cid
                all_messages.append(tagged)

            # Use the earliest created_at
            if merged_created is None or conv.created_at < merged_created:
                merged_created = conv.created_at

        if not all_messages:
            return None

        # Sort by timestamp
        def _sort_key(msg):
            ts = msg.get("timestamp", "")
            try:
                return datetime.fromisoformat(ts)
            except (ValueError, TypeError):
                return datetime.min

        all_messages.sort(key=_sort_key)

        merged = Conversation(title=new_title)
        merged.messages = all_messages
        merged.created_at = merged_created or datetime.now().isoformat()
        merged.updated_at = datetime.now().isoformat()
        self.save_conversation(merged)
        return merged

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_conversation(
        self, conversation_id: str, format: str = "txt"
    ) -> Optional[str]:
        """
        Export a conversation to a string.

        Args:
            conversation_id: ID of the conversation to export
            format: Export format ("txt", "json", "md", "html")

        Returns:
            Exported conversation as string
        """
        conversation = self.load_conversation(conversation_id)
        if not conversation:
            return None

        fmt = format.lower()

        if fmt == "json":
            return json.dumps(conversation.to_dict(), indent=2, ensure_ascii=False)

        elif fmt == "md":
            lines = [f"# {conversation.title}\n"]
            for msg in conversation.messages:
                role = msg.get("role", "unknown").upper()
                content = msg.get("content", "")
                lines.append(f"## {role}\n\n{content}\n")
            return "\n".join(lines)

        elif fmt == "html":
            return self._export_html(conversation)

        elif fmt == "txt":
            lines = [f"Conversation: {conversation.title}\n", "=" * 50]
            for msg in conversation.messages:
                role = msg.get("role", "unknown").upper()
                content = msg.get("content", "")
                lines.append(f"\n[{role}]\n{content}")
            return "\n".join(lines)

        return None

    def _export_html(self, conversation: Conversation) -> str:
        """Render a conversation as a basic HTML document."""
        role_icons = {
            "user": "👤",
            "assistant": "🤖",
            "system": "⚙️",
        }
        role_colors = {
            "user": "#e3f2fd",
            "assistant": "#f3e5f5",
            "system": "#e8f5e9",
        }

        msg_html = []
        for msg in conversation.messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            icon = role_icons.get(role, "💬")
            bg = role_colors.get(role, "#f5f5f5")
            ts = msg.get("timestamp", "")
            # Escape basic HTML
            escaped = (
                content.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )
            # Simple paragraph-wrapping
            html_content = "".join(
                f"<p>{line}</p>" if line.strip() else "<br>"
                for line in escaped.split("\n")
            )
            msg_html.append(
                f"""<div class="message {role}" style="background:{bg};padding:10px 14px;margin:8px 0;border-radius:8px;">
                    <div style="font-weight:bold;margin-bottom:4px;">
                        <span style="font-size:1.2em;">{icon}</span>
                        <span style="text-transform:uppercase;margin-left:6px;">{role}</span>
                        <span style="color:#999;font-size:0.8em;margin-left:12px;">{ts}</span>
                    </div>
                    <div style="margin-left:4px;">{html_content}</div>
                </div>"""
            )

        stats = self.get_conversation_stats(conversation.id)
        stat_line = ""
        if stats:
            dur = stats["duration_seconds"]
            dur_str = f"{int(dur // 60)}m {int(dur % 60)}s" if dur else "N/A"
            stat_line = f"<p style='color:#666;font-size:0.85em;'>{stats['message_count']} messages · {dur_str}</p>"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{conversation.title} — Conversation Export</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          max-width: 800px; margin: 20px auto; padding: 0 16px; background: #fafafa; }}
  h1 {{ color: #333; border-bottom: 2px solid #ddd; padding-bottom: 8px; }}
  .message {{ line-height: 1.5; }}
  .message p {{ margin: 6px 0; }}
  pre {{ background: #f4f4f4; padding: 8px; border-radius: 4px; overflow-x: auto; }}
  code {{ background: #f0f0f0; padding: 2px 4px; border-radius: 3px; font-size: 0.9em; }}
</style>
</head>
<body>
<h1>{conversation.title}</h1>
{stat_line}
<div id="messages">
{"".join(msg_html)}
</div>
<hr>
<p style="color:#999;font-size:0.8em;text-align:center;">
Exported from Lithium IDE — {datetime.now().strftime("%Y-%m-%d %H:%M")}
</p>
</body>
</html>"""
        return html


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
