from transformers import AutoModelForCausalLM, AutoTokenizer
from PIL import Image
import base64
import io


class Vision:
    def __init__(self, computer):
        self.computer = computer
        self.model = None # Will load upon first use
        self.tokenizer = None # Will load upon first use

    def load(self):
        print("Open Interpreter will use Moondream (tiny vision model) to describe images to the language model. Set `interpreter.llm.vision_renderer = None` to disable this behavior.")
        print("Alternativley, you can use a vision-supporting LLM and set `interpreter.llm.supports_vision = True`.")
        model_id = "vikhyatk/moondream2"
        revision = "2024-04-02"
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id, trust_remote_code=True, revision=revision
        )
        self.tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision)

    def query(self, query="Describe this image.", base_64=None, path=None, lmc=None):
        """
        Uses Moondream to ask query of the image (which can be a base64, path, or lmc message)
        """

        if self.model == None and self.tokenizer == None:
            self.load()

        if lmc:
            if "base64" in lmc["format"]:
                # # Extract the extension from the format, default to 'png' if not specified
                # if "." in lmc["format"]:
                #     extension = lmc["format"].split(".")[-1]
                # else:
                #     extension = "png"

                # Decode the base64 image
                img_data = base64.b64decode(lmc["content"])
                img = Image.open(io.BytesIO(img_data))

            elif lmc["format"] == "path":
                # Convert to base64
                image_path = lmc["content"]
                img = Image.open(image_path)
        elif base_64:
            img_data = base64.b64decode(base_64)
            img = Image.open(io.BytesIO(img_data))
        elif path:
            img = Image.open(path)

        enc_image = self.model.encode_image(img)
        return self.model.answer_question(enc_image, query, self.tokenizer)
