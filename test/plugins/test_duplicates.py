from unittest.mock import Mock, patch

import pytest

from beets.exceptions import UserError
from beets.test.helper import IOMixin, PluginMixin, TestHelper


class TestDuplicatesPlugin(PluginMixin, TestHelper, IOMixin):
    plugin = "duplicates"

    @pytest.fixture(autouse=True)
    def setup(self):
        self.setup_beets()
        self.dup_item = self.create_item(
            album="Pretend Album",
            albumartist="Pretend Artist",
            artist="Pretend Artist",
            title="Pretend Track",
            genres=["Original Genre"],
            mb_trackid="abc",
            mb_albumid="def",
        )
        try:
            yield
        finally:
            self.teardown_beets()
            self.dup_item = None

    def run_cmd(self, count=False, path=False) -> str:
        args = ["duplicates"]
        if count:
            args.append("--count")
        if path:
            args.append("--path")

        return self.run_with_output(*args).strip()

    def create_dups(self, count: int):
        for _ in range(count):
            self.lib.add(self.dup_item)

    def test_duplicate(self):
        self.create_dups(2)
        out = self.run_cmd()

        assert self.dup_item.artist in out
        assert self.dup_item.album in out
        assert self.dup_item.title in out

    def test_duplicate_path(self):
        self.create_dups(2)
        out = self.run_cmd(path=True)

        assert str(self.dup_item.filepath) in out

    def test_duplicate_with_count(self):
        self.create_dups(4)
        out = self.run_cmd(count=True)

        assert self.dup_item.artist in out
        assert self.dup_item.album in out
        assert self.dup_item.title in out
        assert out.endswith("3")

    def test_duplicate_path_with_count(self):
        self.create_dups(6)
        out = self.run_cmd(count=True, path=True)

        assert str(self.dup_item.filepath) in out
        assert out.endswith("5")

    def add_dups(self, count: int = 2, **values):
        """Add `count` library items that share the same MusicBrainz ids."""
        values = {"mb_trackid": "abc", "mb_albumid": "def", **values}
        return [self.add_item(**values) for _ in range(count)]

    def add_dup_fixtures(self):
        """Add two duplicate items that have real files on disk."""
        items = self.add_item_fixtures(count=2)
        for item in items:
            item.mb_trackid = "abc"
            item.mb_albumid = "def"
            item.store()
        return items

    def test_query_without_matches(self):
        self.create_dups(2)
        out = self.run_with_output("duplicates", "title:nothing-matches")

        assert out.strip() == ""

    def test_tag(self):
        first, second = self.add_dups()
        self.run_with_output("duplicates", "--tag", "flag=dup")

        assert self.lib.get_item(first.id).get("flag") is None
        assert self.lib.get_item(second.id)["flag"] == "dup"

    def test_tag_invalid(self):
        self.add_dups()

        with pytest.raises(UserError, match="can't parse k=v tag"):
            self.run_with_output("duplicates", "--tag", "no-equals-sign")

    def test_remove_keeps_file(self):
        first, second = self.add_dup_fixtures()
        self.run_with_output("duplicates", "--remove")

        assert [i.id for i in self.lib.items()] == [first.id]
        assert second.filepath.exists()

    def test_delete_removes_file(self):
        first, second = self.add_dup_fixtures()
        self.run_with_output("duplicates", "--delete")

        assert [i.id for i in self.lib.items()] == [first.id]
        assert first.filepath.exists()
        assert not second.filepath.exists()

    def test_copy(self, tmp_path):
        second = self.add_dup_fixtures()[1]
        self.run_with_output("duplicates", "--copy", str(tmp_path))

        assert second.filepath.exists()
        assert [p for p in tmp_path.rglob("*") if p.is_file()]

    def test_move(self, tmp_path):
        second = self.add_dup_fixtures()[1]
        old_path = second.filepath
        self.run_with_output("duplicates", "--move", str(tmp_path))

        moved = self.lib.get_item(second.id)
        assert not old_path.exists()
        assert moved.filepath.exists()
        assert tmp_path in moved.filepath.parents

    def test_album(self):
        self.add_album(mb_albumid="def", album="Dup Album")
        self.add_album(mb_albumid="def", album="Dup Album")
        out = self.run_with_output("duplicates", "--album").strip()

        assert out.count("Dup Album") == 1

    def test_full_lists_all_versions(self):
        self.add_dups(3)
        out = self.run_with_output("duplicates", "--full").strip()

        assert len(out.splitlines()) == 3

    def test_tiebreak_keeps_preferred_item(self):
        self.config["duplicates"]["tiebreak"] = {"items": ["bitrate"]}
        self.add_dups(1, bitrate=320000)
        self.add_dups(1, bitrate=128000)
        out = self.run_with_output("duplicates", "-f", "$bitrate").strip()

        # The item with the highest bitrate is kept, the other is reported.
        assert out == "128kbps"

    @pytest.mark.parametrize(
        "args,expected_lines", [((), 1), (("--strict",), 0)]
    )
    def test_strict_needs_all_keys(self, args, expected_lines):
        self.add_dups(2, mb_albumid="")
        out = self.run_with_output("duplicates", *args).strip()

        assert len(out.splitlines()) == expected_lines

    def test_items_without_keys_are_skipped(self):
        self.add_dups(2, mb_trackid="", mb_albumid="")
        out = self.run_with_output("duplicates").strip()

        assert out == ""

    def test_merge_copies_missing_fields(self):
        # The most complete item is kept as the head of the group.
        complete = self.add_item(
            mb_trackid="abc",
            mb_albumid="def",
            year=2000,
            month=1,
            day=2,
            label="A label",
        )
        self.add_item(mb_trackid="abc", mb_albumid="def", comments="a note")
        self.run_with_output("duplicates", "--merge")

        assert self.lib.get_item(complete.id).comments == "a note"

    def test_checksum_groups_by_command_output(self):
        # Items with different ids are duplicates if the command output matches.
        first = self.add_item(mb_trackid="a", mb_albumid="x")
        second = self.add_item(mb_trackid="b", mb_albumid="y")
        output = Mock(stdout=b"same-checksum")

        with patch("beetsplug.duplicates.command_output", return_value=output):
            out = self.run_with_output(
                "duplicates", "--checksum", "myprog {file}"
            ).strip()

        assert len(out.splitlines()) == 1
        # The checksum is cached on the items under the program name.
        assert self.lib.get_item(first.id)["myprog"] == b"same-checksum"
        assert self.lib.get_item(second.id)["myprog"] == b"same-checksum"

        # A second run uses the cached value and does not call the program.
        with patch(
            "beetsplug.duplicates.command_output",
            side_effect=AssertionError("program must not run again"),
        ):
            again = self.run_with_output(
                "duplicates", "--checksum", "myprog {file}"
            ).strip()

        assert again == out
