ffmpeg -i input.mp4 \
  -vf "fps=5,scale=-2:1080" \
  -c:v libx265 \
  -preset slow \
  -crf 30 \
  -c:a aac \
  -ac 1 \
  -b:a 40k \
  -movflags +faststart \
  output.mp4
