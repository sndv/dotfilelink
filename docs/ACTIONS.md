# Actions

## `create`

Create a file by linking, copying or from a URL.

It has the following options:

### `type` | choice

- `auto` (default) - `link` if the source is a file and `sudo` is false, `copy`
  otherwise
- `link` - create symlink to source file
- `copy` - create copy of source file

### `src` | string (required)

Source file path relative to the configuration file or a URL.

### `dest` | string (required)

Destination path.

### `create_dirs` | boolean

If one or more of the directories in the `dest` path do not exist,
create them.

### `src_type` | choice

- `auto` (default) - automatically recognize if the source is a path or URL
- `path` - source is a path
- `url` - source is a URL

### `relink` | choice

Whether to relink if the destination is a symlink, but does not point to
the correct source.

- `allow` (default) - relink only when the `--force` option is given
- `always` - relink whether or not `--force` is given
- `never` - don't relink even when `--force` is given

### `replace` | choice

Whether to replace the destination if it's a file.

- `allow` (default) - replace only when the `--force` option is given
- `always` - replace whether or not `--force` is given
- `never` - don't replace even when `--force` is given

### `backup` | boolean

Whether to backup the original file when it's replaced, enabled by default.

### `mode` | string

Set the given mode to the destination.

*Note: setting mode for symlinks will change the permissions of the source.*

### `dest_type` | choice

- `normal` - destination is a single path
- `glob_single` - destination is a glob which must match a single file
  otherwise it should fail
- `glob_multiple` - **not yet implemented**

## `filecontent`

Ensure given content is present in a file.

It has the following options:

### `dest` | string (required)

Destination file path.

### `content` | string (required)

Content to be added to the file if it's not there.

### `regex` | regular expression

Instead of looking for exact match of the content, look for a match of the
given regular expression and replace it with `content` if found. It must match
the given content. Multiline mode is enabled.

### `after` | regular expression

Insert `content` after the last match of the given regular expression. If it
does not match `content` is inserted in the end of the file. Multiline mode
is enabled.

### `backup` | boolean

Whether to backup the original file before making changes, enabled by default.

## Other options

### `sudo` | boolean

This option can be added to any action and the action will be executed as root.

In this case the order of actions in the configuration file does not exactly
correspond to the order they are executed in -- all sudo actions are executed
first.

Creating links with this option can have security implications, so by default
a copy is created instead of a symlink unless `type: link` is specified
explicitly.
