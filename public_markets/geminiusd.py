from ._gemini import Gemini

class GeminiUSD(Gemini):
    def __init__(self):
        super().__init__("USD", "btcusd")
