## Creativity

This program is also a game: grade a sixth criterion, **Creativity**, out of 10, with the grid below. Here the code is not all that counts: play the game.

A virtual screen is open for you, `DISPLAY` is set. Build the game with the imposed build, `cmake -B build -G Ninja && cmake --build build`, then launch it in the background, `build/city &`. Play it with `xdotool`: `xdotool mousemove 400 300 click 1` clicks, `xdotool mousemove 400 300` alone hovers, `xdotool key 2` presses a key while the pointer is over the window, and `xdotool search --name . getwindowgeometry` tells where the window is. Take a screenshot with `import -window root _judge/play/<name>.png`, then open it, to see what each action did. Try every tool, the preview on hover and a refused placement (an occupied cell, not enough money), let time run, get to the research and the upgrades and check that each upgrade does exactly what it shows, and reach the end of the game, won or bankrupt, if you can. `build/` and your screenshots are the only files you may add.

`_judge/shots/` also holds three screenshots the game took in its test mode, of states long to reach by hand: `roads.png`, a road layout with every shape; `houses.png`, houses with and without a road, and parks; `work.png`, a shop, a factory and a house along one road. Read the code for what playing did not show.

If the game does not build or its window does not open, say so in the reasons and judge the looks from `_judge/shots/` and the code; when that folder is missing too, from the code alone.

{creativity}

Add it to the `criteria` of `_judge/judgement.json`, in the same form: `"Creativity": {"score": 6, "reasons": "…"}`.
