#!/usr/bin/env python3
import sys

from splunklib.modularinput import Argument, Event, EventWriter, Scheme, Script


class ExampleInput(Script):
    def get_scheme(self):
        scheme = Scheme("Example Product")
        scheme.description = "Pull events from Example Product."
        scheme.use_external_validation = True
        scheme.use_single_instance = False
        scheme.streaming_mode = Scheme.streaming_mode_xml
        url = Argument("api_url")
        url.title = "API URL"
        url.data_type = Argument.data_type_string
        url.required_on_create = True
        scheme.add_argument(url)
        return scheme

    def validate_input(self, definition):
        url = definition.parameters.get("api_url", "")
        if not str(url).startswith("https://"):
            raise ValueError("api_url must start with https://")

    def stream_events(self, inputs, ew: EventWriter):
        for name, params in inputs.inputs.items():
            ew.write_event(
                Event(
                    data="{}",
                    stanza=name,
                    sourcetype=params.get("sourcetype", "example:product:json"),
                    index=params.get("index"),
                )
            )


if __name__ == "__main__":
    sys.exit(ExampleInput().run(sys.argv))
