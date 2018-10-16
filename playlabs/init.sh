#!/bin/sh -x
sudo=""
[ "$USER" = "root" ] || sudo=sudo

if which python3; then
    if ! which python; then
        $sudo ln -sfn $(which python3) /usr/bin/python
    fi
    exit 0
fi

if which apt; then
    $sudo apt update -y
    $sudo apt install -y python3
elif which pacman; then
    $sudo pacman -Sy --noconfirm
    $sudo pacman -S --noconfirm python
elif which apk; then
    $sudo apk update
    $sudo apk add python
fi
