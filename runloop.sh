#!/bin/sh

if [ -e RESTART ] then
    rm RESTART
fi

# git pull
/home/pi/.pyenv/versions/thegamebot/bin/python main.py $@
while [ -e RESTART ] do
    rm RESTART
    # git pull
    /home/pi/.pyenv/versions/thegamebot/bin/python main.py $@
done
