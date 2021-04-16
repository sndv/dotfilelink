
from __future__ import annotations

import os
import sys
import glob
import re
import argparse
import hashlib
import shutil
import subprocess
import difflib
from enum import Enum
from datetime import datetime
from typing import List, Dict, Tuple, IO, Any, Optional, Callable, Type

import yaml

from . import __version__


DEFAULT_DOTFILE_CONFIG_NOTEXPANDED = "~/dotfiles/config.yml"
DEFAULT_DOTFILE_CONFIG = os.path.expanduser(DEFAULT_DOTFILE_CONFIG_NOTEXPANDED)

class Print:

    # Set by main()
    VERBOSITY_LEVEL = 0
    COLORS_ENABLED = False

    # If flush is not used, output from the subprocess sudo execution comes
    # at once when the process finishes
    ALWAYS_FLUSH = True

    class ANSI_COLOR(Enum):
        END = "\033[0m"
        BOLD = "\033[1m"
        UNDERLINE = "\033[4m"
        BLACK = "\033[30m"
        RED = "\033[31m"
        GREEN = "\033[32m"
        YELLOW = "\033[33m"
        BLUE = "\033[34m"
        MAGENTA = "\033[35m"
        CYAN = "\033[36m"
        WHITE = "\033[37m"
        BRIGHT_BLACK = "\033[90m"
        BRIGHT_RED = "\033[91m"
        BRIGHT_GREEN = "\033[92m"
        BRIGHT_YELLOW = "\033[93m"
        BRIGHT_BLUE = "\033[94m"
        BRIGHT_MAGENTA = "\033[95m"
        BRIGHT_CYAN = "\033[96m"
        BRIGHT_WHITE = "\033[97m"

    SUCCESS_COLOR = ANSI_COLOR.GREEN
    AS_EXPECTED_COLOR = ANSI_COLOR.BLUE
    FAILURE_COLOR = ANSI_COLOR.RED

    @classmethod
    def print_(cls, *args: Any, **kwargs: Any) -> None:
        if cls.ALWAYS_FLUSH:
            kwargs["flush"] = True
        print(*args, **kwargs)


    @classmethod
    def info(cls, *args: Any, **kwargs: Any) -> None:
        if cls.VERBOSITY_LEVEL >= 0:
            cls.print_(*args, **kwargs)

    @classmethod
    def v(cls, *args: Any, **kwargs: Any) -> None:
        if cls.VERBOSITY_LEVEL >= 1:
            cls.print_(*args, **kwargs)

    @classmethod
    def vv(cls, *args: Any, **kwargs: Any) -> None:
        if cls.VERBOSITY_LEVEL >= 2:
            cls.print_(*args, **kwargs)

    @classmethod
    def color(cls, msg: str, color: ANSI_COLOR, **kwargs: Any) -> None:
        if cls.COLORS_ENABLED:
            cls.print_(f"{color.value}{msg}{cls.ANSI_COLOR.END.value}", **kwargs)
        else:
            cls.print_(msg, **kwargs)

    @classmethod
    def success(cls, msg: str, **kwargs: Any) -> None:
        cls.color(msg, color=cls.SUCCESS_COLOR, **kwargs)

    @classmethod
    def as_expected(cls, msg: str, **kwargs: Any) -> None:
        cls.color(msg, color=cls.AS_EXPECTED_COLOR, **kwargs)

    @classmethod
    def failure(cls, msg: str, **kwargs: Any) -> None:
        cls.color(msg, color=cls.FAILURE_COLOR, **kwargs)


def file_checksum(path: str) -> str:
    with open(path, "rb") as f:
        file_hash = hashlib.blake2b()
        chunk = f.read(8192)
        while chunk:
            file_hash.update(chunk)
            chunk = f.read(8192)
    return file_hash.hexdigest()


class ConfigFileError(Exception):
    pass


class ArgsDefinition:

    class InvalidArguments(Exception):
        pass

    def __init__(self, definition: Dict):
        self.definition = definition

    def parse(self, args: Dict[str, Any]) -> Dict[str, Any]:
        parsed_args = {}

        for arg_name, value in args.items():
            arg_definition = self.definition.get(arg_name)
            if arg_definition is None:
                raise self.InvalidArguments(f"Unexpected argument: {arg_name}")
            expected_type = arg_definition.get("type", str)
            if not isinstance(value, expected_type):
                raise self.InvalidArguments(
                    f"Argument {arg_name!r} expects type {expected_type.__name__!r} but got "
                    f"{type(value).__name__!r} instead (value: {value!r})")
            if "choices" in arg_definition and value not in arg_definition["choices"]:
                raise self.InvalidArguments(
                    f"Value of {arg_name!r} must be one of {arg_definition['choices']}, "
                    f"got {value!r} instead."
                )
            parsed_args[arg_name] = value

        for arg_name, arg in self.definition.items():
            if arg_name in parsed_args:
                continue
            if arg.get("required"):
                raise self.InvalidArguments(f"Missing required argument {arg_name!r}")
            if "default" in arg:
                parsed_args[arg_name] = arg["default"]

        return parsed_args


class Action:
    """
    An action to be executed.
    """

    args_definition: Optional[ArgsDefinition] = None

    class ActionError(Exception):
        pass

    class SourceDoesNotExist(ActionError):
        pass

    def __init__(self, args: Dict[str, Any], local_dir: str, dry_run: bool = False,
                 show_diff: bool = False, force: bool = False):
        if not self.args_definition:
            raise NotImplementedError("Abstract class")
        self.sudo: bool = args.pop("sudo", False)
        self.local_dir = local_dir
        self.dry_run = dry_run
        self.show_diff = show_diff
        self.force = force
        self._parsed_args = self.args_definition.parse(args)

    def execute(self) -> Tuple[str, Print.ANSI_COLOR, Optional[str]]:
        """
        Execute the action.
        """
        raise NotImplementedError("Abstract method")

    def _file_diff(self, src_path: str, dest_path: str) -> Optional[str]:
        if not self.show_diff:
            return None
        Print.vv(f"Generating diff between {src_path!r} and {dest_path!r}.")
        with open(src_path, "r") as fd:
            src_lines = fd.read().splitlines(keepends=True)
        dest_lines = []
        if os.path.exists(dest_path):
            with open(dest_path, "r") as fd:
                dest_lines = fd.read().splitlines(keepends=True)
        return self._lines_diff(dest_lines, src_lines, dest_path, src_path)

    @staticmethod
    def _expanded_path(path: str) -> str:
        """
        Return the given path with expanded homedir and environment
        variables.
        """
        expanded_path = os.path.expanduser(os.path.expandvars(path))
        Print.vv(f"Original path: {path!r}; expanded path: {expanded_path!r}")
        return expanded_path

    @staticmethod
    def _lines_diff(old_lines: List[str], new_lines: List[str],
                    old_path: str, new_path: str) -> str:
        diff = ""
        for diff_line in difflib.unified_diff(old_lines, new_lines, old_path, new_path):
            diff += diff_line
            if not diff_line.endswith("\n"):
                diff += "\n\\ No newline at end of file\n"
        return diff

    def _backup_file(self, path: str) -> None:
        backup_suffix = datetime.now().strftime("%Y%m%d%H%M%S")
        backup_file_name = f"{path}.{backup_suffix}"
        Print.v(f"Backing up {path!r} as {backup_file_name!r}...")
        if self.dry_run:
            return
        try:
            os.rename(path, backup_file_name)
        except OSError as err:
            raise self.ActionError(
                f"Failed to rename file {path!r} to {backup_file_name!r}: {err!s}"
            ) from err


class CreateAction(Action):
    """
    Create a dotfile by linking or copying.
    """

    class CreateActionError(Action.ActionError):
        pass

    class Result(Enum):
        LINK_AS_EXPECTED = "Correct link already exists"
        NEW_LINK_CREATED = "New link created"
        RELINKED = "Incorrect link was relinked"
        RELINKED_BROKEN_LINK = "Broken link was relinked"
        REPLACED_FILE_WITH_LINK = "Replaced file with link"
        FILE_AS_EXPECTED = "Correct file already exists"
        NEW_FILE_CREATED = "New file created"
        REPLACED_LINK_WITH_FILE = "Replaced link with file"
        REPLACED_BROKEN_LINK_WITH_FILE = "Replaced broken link with file"
        REPLACED_FILE = "Replaced file"

    class Args:
        TYPE = "type"
        SRC = "src"
        DEST = "dest"
        RELINK = "relink"
        REPLACE = "replace"
        BACKUP = "backup"
        CREATE_DIRS = "create_dirs"
        DEST_TYPE = "dest_type"

    class TypeArg:
        LINK = "link"
        COPY = "copy"

    class DestTypeArg:
        NORMAL = "normal"
        GLOB_SINGLE = "glob_single"

    class ForceArg:
        ALLOW = "allow"
        ALWAYS = "always"
        NEVER = "never"

    args_definition = ArgsDefinition({
        Args.TYPE: {
            "type": str,
            "choices": [TypeArg.LINK, TypeArg.COPY],
            "required": False,
            "default": TypeArg.LINK,
        },
        Args.SRC: {
            "type": str,
            "required": True,
        },
        Args.DEST: {
            "type": str,
            "required": True,
        },
        Args.RELINK: {
            "type": str,
            "choices": [ForceArg.ALLOW, ForceArg.ALWAYS, ForceArg.NEVER],
            "required": False,
            "default": ForceArg.ALLOW,
        },
        Args.REPLACE: {
            "type": str,
            "choices": [ForceArg.ALLOW, ForceArg.ALWAYS, ForceArg.NEVER],
            "required": False,
            "default": ForceArg.ALLOW,
        },
        Args.BACKUP: {
            "type": bool,
            "required": False,
            "default": True,
        },
        Args.CREATE_DIRS: {
            "type": bool,
            "required": False,
            "default": False,
        },
        Args.DEST_TYPE: {
            "type": str,
            "choices": [DestTypeArg.NORMAL, DestTypeArg.GLOB_SINGLE],
            "required": False,
            "default": DestTypeArg.NORMAL,
        },
    })

    def execute(self) -> Tuple[str, Print.ANSI_COLOR, Optional[str]]:
        source_path = self._source_path()
        dest_path = self._dest_path()
        Print.v(f"Creating {self._parsed_args[self.Args.TYPE]} of {source_path} "
                f"at {self._parsed_args[self.Args.DEST]}")
        if self._parsed_args[self.Args.TYPE] == self.TypeArg.LINK:
            result, diff = self._execute_for_link(source_path, dest_path)
        elif self._parsed_args[self.Args.TYPE] == self.TypeArg.COPY:
            result, diff = self._execute_for_copy(source_path, dest_path)
        else:
            raise RuntimeError("Unreachable")
        message = f"{result.value} {source_path!r} -> {dest_path!r}"
        color = (Print.AS_EXPECTED_COLOR
                 if result in [self.Result.LINK_AS_EXPECTED, self.Result.FILE_AS_EXPECTED]
                 else Print.SUCCESS_COLOR)
        return message, color, diff

    def _can_replace(self) -> bool:
        return (
            self._parsed_args[self.Args.REPLACE] == self.ForceArg.ALWAYS
            or (self._parsed_args[self.Args.REPLACE] == self.ForceArg.ALLOW and self.force)
        )

    def _can_relink(self) -> bool:
        return (
            self._parsed_args[self.Args.RELINK] == self.ForceArg.ALWAYS
            or (self._parsed_args[self.Args.RELINK] == self.ForceArg.ALLOW and self.force)
        )

    def _create_link(self, source_path: str, dest_path: str) -> None:
        if self.dry_run:
            return
        try:
            os.symlink(source_path, dest_path)
        except OSError as err:
            raise self.CreateActionError(
                f"Failed to create link {source_path!r} -> {dest_path!r}: {err!s}"
            ) from err

    def _create_copy(self, source_path: str, dest_path: str) -> None:
        if self.dry_run:
            return
        try:
            shutil.copyfile(source_path, dest_path)
        except OSError as err:
            raise self.CreateActionError(
                f"Failed to copy file: {source_path!r} -> {dest_path!r}: {err!s}"
            ) from err

    def _create_dirs(self, dir_path: str) -> None:
        if self.dry_run:
            return
        try:
            os.makedirs(dir_path)
        except OSError as err:
            raise self.CreateActionError(
                f"Failed to create directories {dir_path!r}: {err!s}"
            ) from err

    def _unlink(self, link_path: str) -> None:
        if self.dry_run:
            return
        try:
            os.unlink(link_path)
        except OSError as err:
            raise self.CreateActionError(f"Failed to remove link: {link_path!r}: {err!s}") from err

    def _relink(self, source_path: str, dest_path: str, current_source_path: str) -> None:
        if not self._can_relink():
            raise self.CreateActionError(f"Link exists with wrong source: {current_source_path!r} "
                                         f"-> {dest_path!r} instead of {source_path!r}")
        Print.v("Relinking to correct source...")
        if self.dry_run:
            return
        self._unlink(dest_path)
        self._create_link(source_path, dest_path)

    def _replace_link(self, source_path: str, dest_path: str) -> None:
        if not self._can_replace():
            raise self.CreateActionError(
                f"Can't create copy, destination exists as link: {dest_path!r}"
            )
        Print.v("Replacing link with file...")
        if self.dry_run:
            return
        self._unlink(dest_path)
        self._create_copy(source_path, dest_path)

    def _replace_file(self, source_path: str, dest_path: str,
                      create_fn: Callable[[str, str], None]) -> None:
        if not self._can_replace():
            raise self.CreateActionError(
                f"Can't create link or copy, destination file exists: {dest_path!r}"
            )
        Print.v(f"Replacing file {dest_path!r}...")
        if self._parsed_args[self.Args.BACKUP]:
            self._backup_file(dest_path)
        elif not self.dry_run:
            # Backup will rename the file, so remove only if not backed up
            try:
                os.remove(dest_path)
            except OSError as err:
                raise self.CreateActionError(
                    f"Failed to remove file {dest_path!r}: {err!s}"
                ) from err
        create_fn(source_path, dest_path)

    def _create_with_dir(self, source_path: str, dest_path: str,
                         create_fn: Callable[[str, str], None]) -> None:
        dest_directory = os.path.dirname(dest_path)
        if not os.path.isdir(dest_directory):
            if self._parsed_args[self.Args.CREATE_DIRS]:
                self._create_dirs(dest_directory)
            else:
                raise self.CreateActionError(f"Directory does not exist: {dest_path!r}")
        Print.v("Creating new link/copy...")
        create_fn(source_path, dest_path)

    def _execute_for_link(self, source_path: str, dest_path: str) -> Tuple[Result, Optional[str]]:
        if os.path.exists(dest_path):
            if os.path.islink(dest_path):
                link_source = os.readlink(dest_path)
                if link_source == source_path:
                    Print.v("Correct link already exists.")
                    return self.Result.LINK_AS_EXPECTED, None
                diff = self._file_diff(source_path, dest_path)
                self._relink(source_path, dest_path, link_source)
                return self.Result.RELINKED, diff
            if os.path.isfile(dest_path):
                diff = self._file_diff(source_path, dest_path)
                self._replace_file(source_path, dest_path, self._create_link)
                return self.Result.REPLACED_FILE_WITH_LINK, diff
            raise self.CreateActionError(
                f"Destination exists but it's not a file or link, not replacing: {dest_path!r}"
            )
        diff = self._file_diff(source_path, dest_path)
        if os.path.islink(dest_path):  # Broken link
            link_source = os.readlink(dest_path)
            Print.v(f"Found broken link {link_source!r} -> {dest_path!r}")
            self._relink(source_path, dest_path, link_source)
            return self.Result.RELINKED_BROKEN_LINK, diff
        self._create_with_dir(source_path, dest_path, self._create_link)
        return self.Result.NEW_LINK_CREATED, diff

    def _execute_for_copy(self, source_path: str, dest_path: str) -> Tuple[Result, Optional[str]]:
        if os.path.exists(dest_path):
            if os.path.islink(dest_path):
                diff = self._file_diff(source_path, dest_path)
                self._replace_link(source_path, dest_path)
                return self.Result.REPLACED_LINK_WITH_FILE, diff
            if os.path.isfile(dest_path):
                if file_checksum(source_path) == file_checksum(dest_path):
                    Print.v("Correct file already exists.")
                    return self.Result.FILE_AS_EXPECTED, None
                diff = self._file_diff(source_path, dest_path)
                self._replace_file(source_path, dest_path, self._create_copy)
                return self.Result.REPLACED_FILE, diff
            raise self.CreateActionError(
                f"Destination exists but it's not a file or link, not replacing: {dest_path!r}"
            )
        diff = self._file_diff(source_path, dest_path)
        if os.path.islink(dest_path):  # Broken link
            Print.v(f"Found broken link {dest_path!r}")
            self._replace_link(source_path, dest_path)
            return self.Result.REPLACED_BROKEN_LINK_WITH_FILE, diff
        self._create_with_dir(source_path, dest_path, self._create_copy)
        return self.Result.NEW_FILE_CREATED, diff

    def _absolute_path(self, path: str) -> str:
        """
        Return the given path as absolute path.
        """
        return os.path.normpath(os.path.join(self.local_dir, path))

    def _source_path(self) -> str:
        """
        Ensure that the source file exists and return its absolute path.
        """
        source_path = self._absolute_path(self._expanded_path(self._parsed_args[self.Args.SRC]))
        if not os.path.isfile(source_path):
            source_path_text = (
                repr(self._parsed_args[self.Args.SRC])
                + (f" ({source_path!r})" if self._parsed_args[self.Args.SRC] != source_path else "")
            )
            raise self.SourceDoesNotExist(f"Source file {source_path_text} not found.")
        return source_path

    def _dest_path(self) -> str:
        expanded_path = self._expanded_path(self._parsed_args[self.Args.DEST])
        if self._parsed_args[self.Args.DEST_TYPE] == self.DestTypeArg.NORMAL:
            return self._absolute_path(expanded_path)
        if self._parsed_args[self.Args.DEST_TYPE] == self.DestTypeArg.GLOB_SINGLE:
            if set(os.path.basename(expanded_path)) & set("*?[]"):
                raise self.CreateActionError(f"Glob patterns are not yet supported in the file "
                                             f"name: {self._parsed_args[self.Args.DEST]!r}")
            dest_dir_pattern = os.path.dirname(expanded_path)
            dest_dir_list = glob.glob(dest_dir_pattern)
            if len(dest_dir_list) == 0:
                raise self.CreateActionError(
                    f"No directory matched glob pattern: {dest_dir_pattern!r} "
                    f"(dest: {self._parsed_args[self.Args.DEST]!r})"
                )
            if len(dest_dir_list) > 1:
                raise self.CreateActionError(
                    f"Multiple matches for {self.Args.DEST_TYPE}='{self.DestTypeArg.GLOB_SINGLE}': "
                    "{dest_dir_list!r} (dest: {self._parsed_args[self.Args.DEST]!r})"
                )
            dest_path = os.path.join(dest_dir_list[0], os.path.basename(expanded_path))
            return self._absolute_path(dest_path)
        raise RuntimeError("Unreachable")


class FileContentAction(Action):
    """
    Ensure given content is present in a file.
    """

    class FileContentActionError(Action.ActionError):
        pass

    class Args:
        DEST = "dest"
        CONTENT = "content"
        REGEX = "regex"
        AFTER = "after"
        BACKUP = "backup"

    args_definition = ArgsDefinition({
        Args.DEST: {
            "type": str,
            "required": True,
        },
        Args.CONTENT: {
            "type": str,
            "required": True,
        },
        Args.REGEX: {
            "type": str,
            "required": False,
            "default": None,
        },
        Args.AFTER: {
            "type": str,
            "required": False,
            "default": None,
        },
        Args.BACKUP: {
            "type": bool,
            "required": False,
            "default": True,
        },
    })

    def _compile_regex(self, regex: str) -> re.Pattern:
        try:
            return re.compile(regex, flags=re.MULTILINE)
        except re.error as err:
            Print.v(f"Compiling regular expression {regex!r} failed with error: {err!s}")
            raise self.FileContentActionError("Invalid regular expression {regex!r}: {err!s}")

    def execute(self) -> Tuple[str, Print.ANSI_COLOR, Optional[str]]:
        dest_path = self._expanded_path(self._parsed_args[self.Args.DEST])
        if not os.path.exists(dest_path):
            raise self.FileContentActionError(f"Destination file does not exist: {dest_path}")
        if not os.path.isfile(dest_path):
            raise self.FileContentActionError(f"Destination path is not a file: {dest_path}")

        with open(dest_path, "r") as fh:
            file_content = fh.read()

        head, main_content = self._split_on_after_regex(file_content)
        before_match, after_match, matched = \
            self._split_around_content_match(main_content, dest_path)
        new_content = head + before_match + self._parsed_args[self.Args.CONTENT] + after_match
        diff: Optional[str] = None

        if file_content != new_content:
            if self.show_diff:
                diff = self._lines_diff(
                    file_content.splitlines(keepends=True),
                    new_content.splitlines(keepends=True),
                    dest_path,
                    f"{dest_path} (updated)",
                )
            self._backup_file(dest_path)
            if not self.dry_run:
                Print.v(f"Applying file content changes to: {dest_path}")
                with open(dest_path, "w") as fh:
                    fh.write(new_content)

            message = (f"File content updated: {dest_path!r}" if matched
                       else f"File content added: {dest_path!r}")
            color = Print.SUCCESS_COLOR
        else:
            message = f"File contents already as expected: {dest_path!r}"
            color = Print.AS_EXPECTED_COLOR
        return message, color, diff

    def _split_on_after_regex(self, content: str) -> Tuple[str, str]:
        if self._parsed_args[self.Args.AFTER] is None:
            return "", content
        after_regex = self._compile_regex(self._parsed_args[self.Args.AFTER])
        after_matches = list(after_regex.finditer(content))
        if len(after_matches) == 0:
            return "", content
        split_idx = after_matches[-1].end()
        return content[:split_idx], content[split_idx:]

    def _split_around_content_match(self, initial_content: str,
                                    dest_path: str) -> Tuple[str, str, bool]:
        if self._parsed_args[self.Args.REGEX] is not None:
            Print.vv(f"Using content regex: {self._parsed_args[self.Args.REGEX]}")
            content_regex = self._compile_regex(self._parsed_args[self.Args.REGEX])
            if not content_regex.match(self._parsed_args[self.Args.CONTENT]):
                raise self.FileContentActionError(
                    f"Given content does not match the regular expression (file: {dest_path!r})"
                )
            matches = list(content_regex.finditer(initial_content))
            if len(matches) == 0:
                return initial_content, "", False
            idx_start = matches[-1].start()
            idx_end = matches[-1].end()
            return initial_content[:idx_start], initial_content[idx_end:], True
        new_content = self._parsed_args[self.Args.CONTENT]
        idx_start = initial_content.rfind(new_content)
        if idx_start == -1:
            return initial_content, "", False
        return initial_content[:idx_start], initial_content[idx_start+len(new_content):], True


ACTIONS_MAP: Dict[str, Type[Action]] = {
    "create": CreateAction,
    "filecontent": FileContentAction,
}


def parse_args(args_list: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--version",
        "-V",
        action="store_true",
        help="print version and exit",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="count",
        default=0,
        help="verbose mode; specifing the option multiple times increases the verbosity",
    )
    parser.add_argument(
        "--sudo-only",
        action="store_true",
    )
    parser.add_argument(
        "--config-file",
        nargs="?",
        default=DEFAULT_DOTFILE_CONFIG,
        type=argparse.FileType("r"),
        help=f"dotfiles yaml configuration file; default is {DEFAULT_DOTFILE_CONFIG_NOTEXPANDED}",
    )
    parser.add_argument(
        "--color",
        default="auto",
        choices=["always", "auto", "never"],
        help="colorize the output; can be 'always' (default), 'auto', or 'never'",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="don't make changes, only show what will be done",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="show the differences in changed files; works great with --dry-run"

    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="overwrite existing files by default",
    )
    args = parser.parse_args(args_list)
    return args


def parse_yaml_file(fh: IO[str]) -> Any:
    try:
        result = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        Print.failure(f"Error while parsing yaml configuration file {fh.name}:\n{exc}",
                      file=sys.stderr)
        sys.exit(1)
    return result


def _parse_configuraiton(config: Any, local_dir: str, dry_run: bool = False,
                         show_diff: bool = False, force: bool = False) -> List[Action]:
    if not isinstance(config, list):
        raise ConfigFileError("Invalid configuraiton file format: expected list of actions")
    actions: List[Action] = []
    for action_dict in config:
        if len(action_dict) != 1:
            raise ConfigFileError(f"Single action name expected, got: {list(action_dict.keys())}")
        action_name, action_args_list = list(action_dict.items())[0]
        if action_name not in ACTIONS_MAP:
            raise ConfigFileError(f"Invalid action: {action_name}")
        for action_args in action_args_list:
            action = ACTIONS_MAP[action_name](action_args, local_dir=local_dir, dry_run=dry_run,
                                              show_diff=show_diff, force=force)
            actions.append(action)

    return actions


def parse_configuraiton(config: Any, local_dir: str, dry_run: bool = False,
                        show_diff: bool = False, force: bool = False) -> List[Action]:
    try:
        return _parse_configuraiton(config, local_dir, dry_run=dry_run, show_diff=show_diff,
                                    force=force)
    except (ConfigFileError, ArgsDefinition.InvalidArguments) as e:
        Print.failure(f"Configuration file error: {e}")
        sys.exit(1)


def execute_dotfilelink_with_sudo() -> int:
    colors = "always" if Print.COLORS_ENABLED else "never"
    command = [
        "sudo", sys.executable, __file__,
        *sys.argv[1:],
        "--color", colors,
        "--sudo-only",
    ]
    if "--config-file" not in command:
        command += ["--config-file", DEFAULT_DOTFILE_CONFIG]
    process = subprocess.Popen(command, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdout is not None and process.stderr is not None

    return_code = None
    while True:
        return_code = process.poll()
        while stdout_line := process.stdout.readline():
            Print.print_(stdout_line.decode(), end="")
        while stderr_line := process.stderr.readline():
            Print.print_(stderr_line.decode(), end="", file=sys.stderr)
        if return_code is not None:
            break

    return return_code


def main() -> None:
    args = parse_args(sys.argv[1:])
    Print.VERBOSITY_LEVEL = args.verbose
    if args.color == "always":
        Print.COLORS_ENABLED = True
    elif args.color == "auto":
        Print.COLORS_ENABLED = sys.stdout.isatty()
    else:
        Print.COLORS_ENABLED = False

    if args.version:
        Print.info(f"dotfilelink v{__version__}")
        sys.exit(0)

    am_root = os.geteuid() == 0
    if args.sudo_only and not am_root:
        Print.failure("The '--sudo-only' mode can only be run as root.")
        sys.exit(1)

    config = parse_yaml_file(args.config_file)
    # Use the configuration file local directory when resolving paths
    config_local_dir = os.path.dirname(os.path.abspath(args.config_file.name))
    actions = parse_configuraiton(config, local_dir=config_local_dir, dry_run=args.dry_run,
                                  show_diff=args.diff, force=args.force)
    non_sudo_actions = [action for action in actions if not action.sudo]
    sudo_actions = [action for action in actions if action.sudo]

    if args.sudo_only:
        actions_list = sudo_actions
        Print.vv(f"Executing {len(sudo_actions)} sudo actions (sudo-only mode).")
    else:
        # If we are root execute all actions like normal
        actions_list = actions if am_root else non_sudo_actions
        Print.v(f"Executing {len(actions)} actions, sudo: {len(sudo_actions)}, "
                f"non-sudo: {len(non_sudo_actions)}.")

    initial_task_number = 1
    success = True

    if not args.sudo_only and not am_root and sudo_actions:
        Print.vv("Starting new process for sudo actions")
        return_code = execute_dotfilelink_with_sudo()
        success = return_code == 0
        initial_task_number = len(sudo_actions) + 1

    for i, action in enumerate(actions_list):
        task_number = i + initial_task_number
        sudo_msg = " (sudo)" if action.sudo else ""
        try:
            message, color, diff = action.execute()
        except Action.ActionError as err:
            Print.failure(f"[{task_number}/{len(actions)}] {err!s}{sudo_msg}")
            success = False
        else:
            Print.color(f"[{task_number}/{len(actions)}] {message}{sudo_msg}", color)
            if diff:
                sys.stdout.write(diff)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
