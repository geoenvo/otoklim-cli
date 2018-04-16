#!/usr/bin/env bash

source ~/.virtualenvs/otoklim/bin/activate
Xvfb :99 -ac -noreset & 
export DISPLAY=:99
