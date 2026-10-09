# Worship concert video (fully synthetic)

`render.py` generates a gospel-concert worship video entirely in code — no stock
footage, no real people or venues — and lays it over a music track. Scene cuts,
light pulses and the crowd's sway are driven by the track's energy and tempo.

```sh
python3 render.py music.mp3 worship_concert_ai.mp4            # 1920x1080, 30 fps
python3 render.py music.mp3 previews/ --frames 60,200,400      # quick stills
```

Needs `ffmpeg`, `numpy`, `Pillow`.

## Shot list (follows the music's four sections)

| # | Shot | What happens |
|---|------|--------------|
| 1 | Wide, slow push-in | Female lead in a flowing gown, backlit under a glowing cross; robed choir sways in unison; the congregation's hands rise row by row |
| 2 | Close, low angle | The lead, head lifted, mic at her lips, free hand slowly rising toward the light; golden dust drifts |
| 3 | Inside the crowd, lateral pan | Worshippers in three depth layers with hands lifted and heads tilted back, one kneeling in surrender |
| 4 | Wide finale | Light bursts open behind the stage, every hand is up, fade to black |

## Photoreal upgrade: prompts for an AI video model

To get photoreal footage like the reference, generate one clip per shot in Kling,
Veo, Sora or Runway (16:9, 1080p, about 4 s each), then cut them to the music:

1. *Cinematic wide shot of a grand gospel worship concert, a Black female lead singer in a
   flowing white-and-gold gown center stage holding a microphone, robed gospel choir swaying
   behind her, glowing cross of light on the back wall, volumetric golden stage beams through
   haze, congregation silhouettes in the foreground slowly raising their hands, slow dolly
   push-in, warm gold and violet palette, anamorphic, shallow depth of field, 4K.*
2. *Close-up of a Black female gospel singer with braided hair in an elegant updo, eyes
   closed, a tear on her cheek, singing passionately into a microphone, one hand slowly
   lifting toward a bright golden backlight, floating golden dust particles, emotional,
   reverent, cinematic lighting, slow push-in, 4K.*
3. *Inside a worship concert crowd, diverse worshippers seen from behind and in profile with
   hands lifted high, heads tilted back, eyes closed, some crying, one woman kneeling in
   prayer, swaying to the music, golden stage light and violet haze ahead, slow lateral
   tracking shot, emotional, 4K.*
4. *Epic wide shot of a gospel concert climax, the female lead with both arms spread wide,
   blinding golden light bursting from behind the stage, the whole congregation with hands
   raised, light rays and glowing particles, awe and joy, slow crane up, 4K.*

Assemble the generated clips over the track (cut points match `render.py`'s analysis):

```sh
ffmpeg -i shot1.mp4 -i shot2.mp4 -i shot3.mp4 -i shot4.mp4 -i music.mp3 -filter_complex \
 "[0:v]trim=0:3.93,setpts=PTS-STARTPTS[a];[1:v]trim=0:4.67,setpts=PTS-STARTPTS[b];\
  [2:v]trim=0:3.6,setpts=PTS-STARTPTS[c];[3:v]trim=0:3.17,setpts=PTS-STARTPTS[d];\
  [a][b][c][d]concat=n=4:v=1,scale=1920:1080,fps=30[v]" \
 -map "[v]" -map 4:a -c:v libx264 -crf 17 -c:a aac -shortest worship_photoreal.mp4
```
