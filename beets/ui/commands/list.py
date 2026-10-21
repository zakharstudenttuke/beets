"""The 'list' command: query and show library contents."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from beets import ui

if TYPE_CHECKING:
    from collections.abc import Sequence

    from beets.library import Album, Library


class ListCLIOpts(Protocol):
    album: bool
    limit: int | None


def list_items(
    lib: Library, query: Sequence[str], opts: ListCLIOpts, fmt: str = ""
) -> None:
    """Print out items in lib matching query. If album, then search for
    albums instead of single items.
    """
    if opts.album:
        for _album in lib.albums(query, limit=opts.limit):
            ui.print_(format(_album, fmt))
    else:
        # Formatting an item loads its album, so share one Album object between
        # the items of an album instead of querying the database for each.
        albums: dict[int | None, Album | None] = {}
        for item in lib.items(query, limit=opts.limit):
            if item.album_id in albums:
                item._cached_album = albums[item.album_id]
            else:
                albums[item.album_id] = item._cached_album
            ui.print_(format(item, fmt))


def list_func(lib: Library, opts: ListCLIOpts, args: list[str]) -> None:
    list_items(lib, args, opts)


list_cmd = ui.Subcommand("list", help="query the library", aliases=("ls",))
list_cmd.parser.set_usage(
    list_cmd.parser.get_usage().rstrip()
    + "\nExample: %prog -f '$album: $title' artist:beatles"
)
list_cmd.parser.add_all_common_options()
list_cmd.parser.add_limit_option()
list_cmd.func = list_func
