# Dotfilelink

A simple tool for installing dotfiles. Supports changes to files requiring
root access.

## Install

With uv/uvx:

```sh
uv tool install git+https://github.com/sndv/dotfilelink
```

Or with pip/pipx:

```sh
pipx install git+https://github.com/sndv/dotfilelink
```

## Usage

```sh
# Install dotfiles
dotfilelink -c ~/dotfiles/config.yml

# Config file can also be specified with environment variable
export DOTFILELINK_CONFIG="$HOME/dotfiles/config.yml"

# Install dotfiles, replacing existing files
dotfilelink --force

# Only show what will be done
dotfilelink --dry-run

# Show what will be done including difference in changed files
dotfilelink --dry-run --diff
```

## Configuration

How dotfiles should be installed is defined in a YAML configuration file, by
default `~/dotfiles/config.yml`.

It consists of a list of actions, each action is a list of targets the action
should be applied to.

For documentation of all actions and their options see [ACTIONS.md](docs/ACTIONS.md).

## Example configuration file

```yaml
---

# Dotfiles directory for this example:
#
# dotfiles
# ├── aliases
# ├── firefox.user.js
# ├── gitconfig
# ├── global
# │   └── keyd.conf
# └── ssh-config


# Create symlink ~/.gitconfig pointing to gitconfig and ~/.vimrc pointing
# to vimrc; source paths are relative to the config file location.
# Environment variables and '~' can be used in the paths.
- create:
    - src: gitconfig
      dest: ~/.gitconfig
    - src: vimrc
      dest: $HOME/.vimrc

# Create a copy instead of a symlink
- create:
    - src: ssh-config
      dest: ~/.ssh/config
      type: copy
      # Set mode to 600 after creating file
      mode: '600'
      # Create the ~/.ssh directory if it does not exist
      create_dirs: yes

# Create a file from a URL
- create:
    - src: https://raw.githubusercontent.com/mathiasbynens/dotfiles/main/.screenrc
      dest: ~/.screenrc

# Only part of a file can be changed using 'filecontent'.
# For example keep the distribution's original bashrc file and only add a line
# to source custom aliases from a separate file.
- create:
    - src: aliases
      dest: ~/.aliases
- filecontent:
    - dest: ~/.bashrc
      content: "[[ -f ~/.aliases ]] && source ~/.aliases\n"

# If the exact destination path is not known, globs can be used. When
# 'glob_single' is used, exactly one match is expected from the glob pattern in
# order to ensure no unwanted changes are made.
- create:
    - src: firefox.user.js
      dest_type: glob_single
      dest: ~/.mozilla/firefox/*.default-release/user.js

# The 'sudo' option can be used to execute an action as root, allowing it to
# change files that only root has write access to.
- create:
  - src: global/keyd.conf
    dest: /etc/keyd/default.conf
    type: copy
    sudo: yes
```
