"""Regression tests for the Claude Code PreToolUse hook settings DogBuild writes.

Claude Code rejects `hooks.PreToolUse` unless every entry is a matcher group
with a nested `hooks` array. An earlier launcher wrote a flat list of command
hooks, which produced a Settings Error on startup and clobbered manual fixes.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from psk import launcher


def read_settings(root):
    """Parse the generated settings file exactly as Claude Code would."""
    return json.loads(
        (Path(root) / ".claude" / "settings.local.json").read_text(encoding="utf-8")
    )


def assert_valid_shape(test, settings):
    """Assert the Claude Code PreToolUse contract holds for *settings*."""
    test.assertIsInstance(settings, dict)
    test.assertIsInstance(settings.get("hooks"), dict)

    pre = settings["hooks"].get("PreToolUse")
    test.assertIsInstance(pre, list, "hooks.PreToolUse must be an array")
    test.assertTrue(pre, "hooks.PreToolUse must not be empty")

    for entry in pre:
        test.assertIsInstance(entry, dict)
        test.assertIn("matcher", entry, f"matcher-group missing 'matcher': {entry}")
        test.assertIsInstance(entry["matcher"], str)
        test.assertIn("hooks", entry, f"matcher-group missing 'hooks': {entry}")
        test.assertIsInstance(entry["hooks"], list, "nested hooks must be an array")
        for hook in entry["hooks"]:
            test.assertIsInstance(hook, dict)
            test.assertEqual(hook.get("type"), "command")
            test.assertIsInstance(hook.get("command"), str)


def count_dogbuild_hooks(settings):
    """Count DogBuild command hooks anywhere under hooks.PreToolUse."""
    total = 0
    for entry in settings.get("hooks", {}).get("PreToolUse", []):
        for hook in entry.get("hooks", []) if isinstance(entry, dict) else []:
            if launcher.DOGBUILD_HOOK_MARKER in str(hook.get("command", "")):
                total += 1
    return total


class HookConfigShapeTest(unittest.TestCase):
    """build_hooks_config() must emit the supported nesting."""

    def test_pretooluse_is_matcher_group_array(self):
        assert_valid_shape(self, launcher.build_hooks_config())

    def test_group_contains_dogbuild_command_hook(self):
        config = launcher.build_hooks_config()
        group = config["hooks"]["PreToolUse"][0]
        self.assertEqual(group["matcher"], launcher.DOGBUILD_HOOK_MATCHER)
        self.assertEqual(len(group["hooks"]), 1)
        self.assertIn(launcher.DOGBUILD_HOOK_MARKER, group["hooks"][0]["command"])

    def test_no_bare_command_hook_at_group_level(self):
        """The old broken shape put type/command directly in the group."""
        for entry in launcher.build_hooks_config()["hooks"]["PreToolUse"]:
            self.assertNotIn("type", entry)
            self.assertNotIn("command", entry)


class WriteHooksConfigTest(unittest.TestCase):
    """write_hooks_config() must merge, not overwrite."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="psk-hooks-")
        self.settings_file = Path(self.root) / ".claude" / "settings.local.json"

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _seed(self, data):
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        self.settings_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def test_generated_file_parses_and_is_valid(self):
        launcher.write_hooks_config(self.root)
        assert_valid_shape(self, read_settings(self.root))

    def test_dogbuild_hook_present_exactly_once(self):
        launcher.write_hooks_config(self.root)
        self.assertEqual(count_dogbuild_hooks(read_settings(self.root)), 1)

    def test_repeated_generation_is_idempotent(self):
        launcher.write_hooks_config(self.root)
        first = self.settings_file.read_text(encoding="utf-8")
        for _ in range(3):
            launcher.write_hooks_config(self.root)
        self.assertEqual(self.settings_file.read_text(encoding="utf-8"), first)
        self.assertEqual(count_dogbuild_hooks(read_settings(self.root)), 1)
        assert_valid_shape(self, read_settings(self.root))

    def test_unrelated_settings_survive(self):
        self._seed({
            "permissions": {
                "allow": ["Read", "Bash(ls:*)"],
                "deny": ["Bash(git push:*)"],
                "defaultMode": "acceptEdits",
            },
            "env": {"FOO": "bar"},
        })
        launcher.write_hooks_config(self.root)
        settings = read_settings(self.root)
        self.assertEqual(settings["permissions"]["allow"], ["Read", "Bash(ls:*)"])
        self.assertEqual(settings["permissions"]["deny"], ["Bash(git push:*)"])
        self.assertEqual(settings["permissions"]["defaultMode"], "acceptEdits")
        self.assertEqual(settings["env"], {"FOO": "bar"})
        assert_valid_shape(self, settings)

    def test_unrelated_pretooluse_groups_survive(self):
        other = {
            "matcher": "Bash",
            "hooks": [{"type": "command", "command": "echo audit"}],
        }
        self._seed({"hooks": {"PreToolUse": [other]}})
        launcher.write_hooks_config(self.root)
        settings = read_settings(self.root)
        self.assertIn(other, settings["hooks"]["PreToolUse"])
        self.assertEqual(count_dogbuild_hooks(settings), 1)
        assert_valid_shape(self, settings)

    def test_unrelated_hook_events_survive(self):
        post = [{"matcher": "*", "hooks": [{"type": "command", "command": "echo post"}]}]
        self._seed({"hooks": {"PostToolUse": post}})
        launcher.write_hooks_config(self.root)
        settings = read_settings(self.root)
        self.assertEqual(settings["hooks"]["PostToolUse"], post)
        assert_valid_shape(self, settings)

    def test_unrelated_hook_in_same_matcher_group_survives(self):
        """A shared "*" group keeps its own hooks and gains ours exactly once."""
        theirs = {"type": "command", "command": "echo theirs"}
        self._seed({"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [theirs]}]}})
        launcher.write_hooks_config(self.root)
        launcher.write_hooks_config(self.root)
        settings = read_settings(self.root)
        groups = settings["hooks"]["PreToolUse"]
        self.assertEqual(len(groups), 1)
        self.assertIn(theirs, groups[0]["hooks"])
        self.assertEqual(count_dogbuild_hooks(settings), 1)
        assert_valid_shape(self, settings)

    def test_legacy_flat_dogbuild_hook_is_repaired(self):
        """The broken shape previously written must be replaced, not kept."""
        self._seed({
            "hooks": {
                "PreToolUse": [
                    {
                        "type": "command",
                        "command": "PYTHONPATH=/old python3 -m psk.governor.broker",
                    }
                ]
            },
            "permissions": {"allow": ["Read"]},
        })
        launcher.write_hooks_config(self.root)
        settings = read_settings(self.root)
        assert_valid_shape(self, settings)
        self.assertEqual(count_dogbuild_hooks(settings), 1)
        self.assertEqual(settings["permissions"]["allow"], ["Read"])

    def test_stale_dogbuild_command_is_replaced_not_appended(self):
        self._seed({
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "PYTHONPATH=/stale python3 -m psk.governor.broker",
                            }
                        ],
                    }
                ]
            }
        })
        launcher.write_hooks_config(self.root)
        settings = read_settings(self.root)
        self.assertEqual(count_dogbuild_hooks(settings), 1)
        commands = [
            h["command"]
            for g in settings["hooks"]["PreToolUse"]
            for h in g["hooks"]
        ]
        self.assertNotIn(
            "PYTHONPATH=/stale python3 -m psk.governor.broker", commands
        )
        self.assertIn(launcher.build_hook_command(), commands)

    def test_dry_run_does_not_write(self):
        merged = launcher.write_hooks_config(self.root, dry_run=True)
        self.assertFalse(self.settings_file.exists())
        assert_valid_shape(self, merged)

    def test_corrupt_file_is_replaced_with_valid_config(self):
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        self.settings_file.write_text("{not json", encoding="utf-8")
        launcher.write_hooks_config(self.root)
        assert_valid_shape(self, read_settings(self.root))


class MergeHooksConfigTest(unittest.TestCase):
    """merge_hooks_config() is the pure core — test it without the filesystem."""

    def test_empty_input(self):
        assert_valid_shape(self, launcher.merge_hooks_config({}))

    def test_non_dict_input(self):
        assert_valid_shape(self, launcher.merge_hooks_config(None))
        assert_valid_shape(self, launcher.merge_hooks_config([1, 2, 3]))

    def test_non_dict_hooks_value(self):
        assert_valid_shape(self, launcher.merge_hooks_config({"hooks": "nope"}))

    def test_non_list_pretooluse_value(self):
        merged = launcher.merge_hooks_config({"hooks": {"PreToolUse": {"a": 1}}})
        assert_valid_shape(self, merged)

    def test_does_not_mutate_input(self):
        original = {"hooks": {"PreToolUse": []}, "permissions": {"allow": []}}
        snapshot = json.dumps(original, sort_keys=True)
        launcher.merge_hooks_config(original)
        self.assertEqual(json.dumps(original, sort_keys=True), snapshot)

    def test_idempotent_across_repeated_merges(self):
        merged = launcher.merge_hooks_config({})
        for _ in range(5):
            merged = launcher.merge_hooks_config(merged)
        assert_valid_shape(self, merged)
        self.assertEqual(count_dogbuild_hooks(merged), 1)


if __name__ == "__main__":
    unittest.main()
