#!/usr/bin/env python3
import sys

from splunklib.searchcommands import (
    Configuration,
    Option,
    StreamingCommand,
    dispatch,
    validators,
)


@Configuration()
class MyCommand(StreamingCommand):
    """Copy one field to 'copied'. Replace this with the real command."""

    field = Option(
        doc="Field to copy",
        require=True,
        validate=validators.Fieldname(),
    )

    def stream(self, records):
        for record in records:
            record["copied"] = record.get(self.field, "")
            yield record


dispatch(MyCommand, sys.argv, sys.stdin, sys.stdout, __name__)
