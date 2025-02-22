from response_parser import *
import gradio as gr


def initialization(state_dict: Dict) -> None:
    if not os.path.exists('cache'):
        os.mkdir('cache')
    if state_dict["bot_backend"] is None:
        state_dict["bot_backend"] = BotBackend()
        if 'OPENAI_API_KEY' in os.environ:
            del os.environ['OPENAI_API_KEY']


def get_bot_backend(state_dict: Dict) -> BotBackend:
    return state_dict["bot_backend"]


def switch_to_gpt4(state_dict: Dict, whether_switch: bool) -> None:
    bot_backend = get_bot_backend(state_dict)
    if whether_switch:
        bot_backend.update_gpt_model_choice("GPT-4")
    else:
        bot_backend.update_gpt_model_choice("GPT-3.5")


def add_text(state_dict: Dict, history: List, text: str) -> Tuple[List, Dict]:
    bot_backend = get_bot_backend(state_dict)
    bot_backend.add_text_message(user_text=text)

    history = history + [(text, None)]

    return history, gr.update(value="", interactive=False)


def add_file(state_dict: Dict, history: List, file) -> List:
    bot_backend = get_bot_backend(state_dict)
    path = file.name
    filename = os.path.basename(path)

    bot_msg = [f'📁[{filename}]', None]
    history.append(bot_msg)

    bot_backend.add_file_message(path=path, bot_msg=bot_msg)

    return history


def undo_upload_file(state_dict: Dict, history: List) -> Tuple[List, Dict]:
    bot_backend = get_bot_backend(state_dict)
    bot_msg = bot_backend.revoke_file()

    if bot_msg is None:
        return history, gr.Button.update(interactive=False)

    else:
        assert history[-1] == bot_msg
        del history[-1]
        if bot_backend.revocable_files:
            return history, gr.Button.update(interactive=True)
        else:
            return history, gr.Button.update(interactive=False)


def refresh_file_display(state_dict: Dict) -> List[str]:
    bot_backend = get_bot_backend(state_dict)
    work_dir = bot_backend.jupyter_work_dir
    filenames = os.listdir(work_dir)
    paths = []
    for filename in filenames:
        paths.append(
            os.path.join(work_dir, filename)
        )
    return paths


def restart_ui(history: List) -> Tuple[List, Dict, Dict, Dict, Dict]:
    history.clear()
    return (
        history,
        gr.Textbox.update(value="", interactive=False),
        gr.Button.update(interactive=False),
        gr.Button.update(interactive=False),
        gr.Button.update(interactive=False)
    )


def restart_bot_backend(state_dict: Dict) -> None:
    bot_backend = get_bot_backend(state_dict)
    bot_backend.restart()


def bot(state_dict: Dict, history: List) -> List:
    bot_backend = get_bot_backend(state_dict)

    while bot_backend.finish_reason in ('new_input', 'function_call'):
        if history[-1][0] is None:
            history.append(
                [None, ""]
            )
        else:
            history[-1][1] = ""

        response = chat_completion(bot_backend=bot_backend)
        for chunk in response:
            history, weather_exit = parse_response(
                chunk=chunk,
                history=history,
                bot_backend=bot_backend
            )
            yield history
            if weather_exit:
                exit(-1)

    yield history


if __name__ == '__main__':
    config = get_config()
    with gr.Blocks(theme=gr.themes.Base()) as block:
        """
        Reference: https://www.gradio.app/guides/creating-a-chatbot-fast
        """
        # UI components
        state = gr.State(value={"bot_backend": None})
        with gr.Tab("Chat"):
            chatbot = gr.Chatbot([], elem_id="chatbot", label="Local Code Interpreter", height=750)
            with gr.Row():
                with gr.Column(scale=0.85):
                    text_box = gr.Textbox(
                        show_label=False,
                        placeholder="Enter text and press enter, or upload a file",
                        container=False
                    )
                with gr.Column(scale=0.15, min_width=0):
                    file_upload_button = gr.UploadButton("📁", file_types=['file'])
            with gr.Row(equal_height=True):
                with gr.Column(scale=0.7):
                    check_box = gr.Checkbox(label="Use GPT-4", interactive=config['model']['GPT-4']['available'])
                    check_box.change(fn=switch_to_gpt4, inputs=[state, check_box])
                with gr.Column(scale=0.15, min_width=0):
                    restart_button = gr.Button(value='🔄 Restart')
                with gr.Column(scale=0.15, min_width=0):
                    undo_file_button = gr.Button(value="↩️Undo upload file", interactive=False)
        with gr.Tab("Files"):
            file_output = gr.Files()

        # Components function binding
        txt_msg = text_box.submit(add_text, [state, chatbot, text_box], [chatbot, text_box], queue=False).then(
            bot, [state, chatbot], chatbot
        )
        txt_msg.then(fn=refresh_file_display, inputs=[state], outputs=[file_output])
        txt_msg.then(lambda: gr.update(interactive=True), None, [text_box], queue=False)
        txt_msg.then(lambda: gr.Button.update(interactive=False), None, [undo_file_button], queue=False)

        file_msg = file_upload_button.upload(
            add_file, [state, chatbot, file_upload_button], [chatbot], queue=False
        ).then(
            bot, [state, chatbot], chatbot
        )
        file_msg.then(lambda: gr.Button.update(interactive=True), None, [undo_file_button], queue=False)
        file_msg.then(fn=refresh_file_display, inputs=[state], outputs=[file_output])

        undo_file_button.click(
            fn=undo_upload_file, inputs=[state, chatbot], outputs=[chatbot, undo_file_button]
        ).then(
            fn=refresh_file_display, inputs=[state], outputs=[file_output]
        )

        restart_button.click(
            fn=restart_ui, inputs=[chatbot],
            outputs=[chatbot, text_box, restart_button, file_upload_button, undo_file_button]
        ).then(
            fn=restart_bot_backend, inputs=[state], queue=False
        ).then(
            fn=refresh_file_display, inputs=[state], outputs=[file_output]
        ).then(
            fn=lambda: (gr.Textbox.update(interactive=True), gr.Button.update(interactive=True),
                        gr.Button.update(interactive=True)),
            inputs=None, outputs=[text_box, restart_button, file_upload_button], queue=False
        )

        block.load(fn=initialization, inputs=[state])

    block.queue()
    block.launch(inbrowser=True)
