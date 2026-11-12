#
# This file is part of the device_xiaomi_mondrian-patch distribution (https://github.com/flakeforever/device_xiaomi_mondrian-patch).
# Copyright (c) 2024 Flakeforever.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#

import curses
import os
import subprocess
import shlex
import argparse

base_dir = os.path.dirname(os.path.abspath(__file__))

# Function to get all patch files in the directory and its subdirectories
def get_patch_files(directory):
    patch_files = []
    for root, _, files in os.walk(directory):
        for file_name in files:
            if file_name.endswith(".patch"):
                file_path = os.path.join(root, file_name)
                patch_files.append(file_path)
    patch_files = sorted(patch_files)
    return patch_files

def convert_to_item(file_name):
    item = {}
    item["full_path"] = file_name

    # Remove base_dir and patch file name, and extract the middle subdirectory
    relative_path = file_name.replace(base_dir, "").strip("/")
    subdirectory = os.path.dirname(relative_path)
    item["subdirectory"] = subdirectory.replace(",", "/")

    # Extract patch file name
    patch_file_name = os.path.basename(file_name)
    item["patch_file_name"] = patch_file_name

    item["enabled"] = 0
    return item

def create_menu(items):
    # Initialize curses
    stdscr = curses.initscr()
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)

    # Set up colors
    if curses.has_colors():
        curses.start_color()
        try:
            curses.use_default_colors()
        except curses.error:
            pass
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(2, curses.COLOR_CYAN, curses.COLOR_BLACK)

    selected_indices = set()
    current_item = 0
    top_item = 0

    def draw_menu():
        nonlocal top_item
        height, width = stdscr.getmaxyx()
        win_h = max(4, height - 2)
        win_w = max(20, width - 2)
        win = curses.newwin(win_h, win_w, 1, 1)
        win.keypad(True)
        win.box()
        win.addnstr(0, 2, "Select patches to enable (use spacebar to toggle)", win_w - 4)
        win.addnstr(1, 2, "Press ENTER to execute all selected patches.", win_w - 4)

        visible = max(1, win_h - 4)
        if current_item < top_item:
            top_item = current_item
        elif current_item >= top_item + visible:
            top_item = current_item - visible + 1
        top_item = max(0, min(top_item, max(0, len(items) - visible)))

        for row in range(visible):
            idx = top_item + row
            if idx >= len(items):
                break
            checkbox = "[X]" if idx in selected_indices else "[ ]"
            line = checkbox + " " + items[idx]["subdirectory"] + "/" + items[idx]["patch_file_name"]
            attr = curses.color_pair(1) if idx == current_item else curses.color_pair(2)
            win.addnstr(3 + row, 2, line, win_w - 4, attr)

        if len(items) > visible:
            pos = "%d/%d" % (current_item + 1, len(items))
            win.addnstr(win_h - 1, max(2, win_w - len(pos) - 2), pos, len(pos))

        win.refresh()
        return win, visible

    def read_key(win):
        # Handle both application-mode (\x1bOB) and normal-mode (\x1b[B)
        # arrow keys.  Some terminals do not honor the smkx sequence.
        key = win.getch()
        if key != 27:
            return key
        seq = ""
        win.timeout(50)
        try:
            for _ in range(3):
                ch = win.getch()
                if ch == -1:
                    break
                seq += chr(ch)
                if ch in (ord('~'), ord('A'), ord('B'), ord('C'), ord('D'),
                          ord('H'), ord('F')):
                    break
        finally:
            win.timeout(-1)
        mapping = {
            "[A": curses.KEY_UP, "OA": curses.KEY_UP,
            "[B": curses.KEY_DOWN, "OB": curses.KEY_DOWN,
            "[C": curses.KEY_RIGHT, "OC": curses.KEY_RIGHT,
            "[D": curses.KEY_LEFT, "OD": curses.KEY_LEFT,
            "[5~": curses.KEY_PPAGE, "[6~": curses.KEY_NPAGE,
            "[H": curses.KEY_HOME, "OH": curses.KEY_HOME,
            "[F": curses.KEY_END, "OF": curses.KEY_END,
        }
        return mapping.get(seq, 27)

    try:
        while True:
            menu_win, visible = draw_menu()
            key = read_key(menu_win)

            if key in (ord('\n'), curses.KEY_ENTER):
                break
            elif key == ord(' '):
                if current_item in selected_indices:
                    selected_indices.remove(current_item)
                else:
                    selected_indices.add(current_item)
            elif key == curses.KEY_UP:
                if current_item > 0:
                    current_item -= 1
            elif key == curses.KEY_DOWN:
                if current_item < len(items) - 1:
                    current_item += 1
            elif key == curses.KEY_PPAGE:
                current_item = max(0, current_item - visible)
            elif key == curses.KEY_NPAGE:
                current_item = min(len(items) - 1, current_item + visible)
            elif key == curses.KEY_HOME:
                current_item = 0
            elif key == curses.KEY_END:
                current_item = len(items) - 1
    finally:
        curses.nocbreak()
        stdscr.keypad(False)
        curses.echo()
        curses.endwin()

    # Update enabled field based on selected indices
    for i, item in enumerate(items):
        item["enabled"] = 1 if i in selected_indices else 0

    return items

def patch_is_applied(repo, patch_path):
    forward = subprocess.run(
        f'git -C {shlex.quote(repo)} apply --check {shlex.quote(patch_path)}',
        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if forward.returncode == 0:
        return False
    reverse = subprocess.run(
        f'git -C {shlex.quote(repo)} apply --reverse --check {shlex.quote(patch_path)}',
        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return reverse.returncode == 0


def apply_patches(items, quiet=False):
    if not quiet:
        items = create_menu(items)
    else:
        # In quiet mode, enable all patches
        for item in items:
            item["enabled"] = 1

    # Print all items
    print("Applying patches:")
    current_path = os.getcwd()
    for item in items:
        if item["enabled"] == 1:
            full_path = os.path.join(current_path, item["full_path"])
            target_repo = os.path.join("..", item["subdirectory"])
            if patch_is_applied(target_repo, full_path):
                print("Already applied, skipping:", full_path)
                continue
            git_command = f'git -C {shlex.quote(target_repo)} am {shlex.quote(full_path)}'
            print("Executing:", git_command)
            result = subprocess.run(git_command, shell=True)
            if result.returncode == 0:
                print("Execute successfully")
            else:
                print("Execute failed")
                subprocess.run(
                    f'git -C {shlex.quote(target_repo)} am --abort',
                    shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if quiet:
                    # In quiet mode, abort on first failure
                    return False
    return True

def main():
    parser = argparse.ArgumentParser(description='Apply patches to the repository')
    parser.add_argument('--quiet', action='store_true', help='Apply all patches without user interaction')
    args = parser.parse_args()

    # Get patch files in the base directory and its subdirectories
    patch_files = get_patch_files(base_dir)

    items = []
    # Print the patch files
    print("Patch files:")
    for patch_file in patch_files:
        item = convert_to_item(patch_file)
        items.append(item)

    success = apply_patches(items, args.quiet)
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())
