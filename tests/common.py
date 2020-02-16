import json


class Request:
    def __init__(self, headers, json_data):
        self.headers = headers
        self.json_data = json_data

    async def json(self):
        return json.loads(self.json_data)
