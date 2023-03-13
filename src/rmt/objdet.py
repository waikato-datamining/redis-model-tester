import gradio as gr
import numpy as np
import redis
import traceback

from io import BytesIO
from opex import ObjectPredictions
from PIL import Image, ImageDraw
from time import sleep


redis_conn = None
redis_pubsub = None
redis_thread = None
preds = None


def predict(host, port, db, channel_in, channel_out, min_score, color, input_img):
    global redis_conn
    global redis_pubsub
    global redis_thread
    global preds

    if redis_conn is None:
        redis_conn = redis.Redis(host, port, db)

    im = Image.fromarray(input_img)
    buf = BytesIO()
    im.save(buf, format="jpeg")

    # handler for listening/outputting
    def anon_handler(message):
        global redis_pubsub
        global preds
        data = message['data']
        preds = ObjectPredictions.from_json_string(data.decode())
        redis_pubsub.close()
        redis_pubsub = None
        redis_thread.stop()

    # subscribe and start listening
    redis_pubsub = redis_conn.pubsub()
    redis_pubsub.psubscribe(**{channel_out: anon_handler})
    redis_conn.publish(channel_in, buf.getvalue())
    redis_thread = redis_pubsub.run_in_thread(sleep_time=0.001)
    while redis_thread.is_alive():
        sleep(0.1)

    # overlay predictions
    if preds is not None:
        overlay = Image.new('RGBA', im.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        modified = False
        for obj in preds.objects:
            if obj.score >= min_score:
                modified = True
                points = [tuple(x) for x in obj.polygon.points]
                draw.polygon(tuple(points), outline=color)
                draw.text((obj.bbox.left, obj.bbox.top), obj.label, fill=color)
        if modified:
            im.paste(overlay, (0, 0), mask=overlay)
        return np.asarray(im), preds.to_json_string()
    else:
        return input_img, "{}"


def main():
    demo = gr.Interface(
        fn=predict,
        inputs=[
            gr.Textbox(label="Host", value="localhost"),
            gr.Number(label="Port", value=6379),
            gr.Number(label="DB", value=0),
            gr.Textbox(label="Channel in", value="opex_in"),
            gr.Textbox(label="Channel out", value="opex_out"),
            gr.Number(label="Minimum score", value=0),
            gr.ColorPicker(label="Color of predictions", value="#ff0000"),
            gr.Image(shape=(200, 200)),
        ],
        outputs=[
            gr.Image(),
            gr.JSON(),
        ])
    demo.launch()


def sys_main():
    """
    Runs the main function using the system cli arguments, and
    returns a system error code.
    :return: 0 for success, 1 for failure.
    :rtype: int
    """
    try:
        main()
        return 0
    except Exception:
        print(traceback.format_exc())
        return 1


if __name__ == '__main__':
    main()
