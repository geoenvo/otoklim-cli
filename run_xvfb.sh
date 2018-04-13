#!/usr/bin/env bash

source ~/.virtualenvs/otoklim/bin/activate
cd $(dirname $0)/otoklim
Xvfb :99 -ac -noreset & 
export DISPLAY=:99
