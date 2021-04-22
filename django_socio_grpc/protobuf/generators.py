import io
import logging

from django.apps import apps
from django.db import models
from rest_framework.utils import model_meta

from django_socio_grpc.mixins import (
    CreateModelMixin,
    DestroyModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
)
from django_socio_grpc.utils.model_extractor import get_model, get_model_fields

logger = logging.getLogger("django_socio_grpc")


class ModelProtoGenerator:
    type_mapping = {
        # Numeric
        models.AutoField.__name__: "int32",
        models.SmallIntegerField.__name__: "int32",
        models.IntegerField.__name__: "int32",
        models.BigIntegerField.__name__: "int64",
        models.PositiveSmallIntegerField.__name__: "int32",
        models.PositiveIntegerField.__name__: "int32",
        models.FloatField.__name__: "float",
        models.DecimalField.__name__: "string",
        # Boolean
        models.BooleanField.__name__: "bool",
        models.NullBooleanField.__name__: "bool",
        # Date and time
        models.DateField.__name__: "string",
        models.TimeField.__name__: "string",
        models.DateTimeField.__name__: "string",
        models.DurationField.__name__: "string",
        # String
        models.CharField.__name__: "string",
        models.TextField.__name__: "string",
        models.EmailField.__name__: "string",
        models.SlugField.__name__: "string",
        models.URLField.__name__: "string",
        models.UUIDField.__name__: "string",
        models.GenericIPAddressField.__name__: "string",
        models.FilePathField.__name__: "string",
        # Default
        models.Field.__name__: "string",
    }

    def __init__(self, app_name, model_name=None):
        self.model_name = model_name
        self.app_name = app_name

        # if there is a model_name that mean we want to generate for only one model
        if self.model_name:
            self.models = [get_model(self.app_name, self.model_name)]
        else:
            app = apps.get_app_config(app_label=self.app_name)
            # INFO - AM - 20/04/2021 - Convert to list to be able to iterate multiple time
            # INFO - AM - 20/04/2021 - Can use tee method to duplicate the generator but I don't see the main goal here
            self.models = list(app.get_models())

        self._writer = _CodeWriter()

    def get_proto(self):
        self._writer.write_line('syntax = "proto3";')
        self._writer.write_line("")
        self._writer.write_line(
            f"package {self.app_name if self.app_name else self.model_name};"
        )
        self._writer.write_line("")
        self._writer.write_line('import "google/protobuf/empty.proto";')
        self._writer.write_line("")
        for model in self.models:
            # we do not want generate code for abstract model
            if model_meta.is_abstract_model(model):
                continue
            self._generate_service(model)

        for model in self.models:
            # we do not want generate code for abstract model
            if model_meta.is_abstract_model(model):
                continue
            self._generate_message(model)
        return self._writer.get_code()

    def _generate_service(self, model):
        grpc_methods = (
            model._meta.grpc_methods
            if hasattr(model, "_meta") and hasattr(model._meta, "grpc_methods")
            else self.get_default_grpc_methods(model)
        )

        if not grpc_methods:
            return

        self._writer.write_line(f"service {model.__name__}Controller {{")
        with self._writer.indent():
            for method_name, method_data in grpc_methods.items():
                request_message = self.construct_method_message(
                    method_data.get("request", dict()), model
                )
                response_message = self.construct_method_message(
                    method_data.get("response", dict()), model
                )
                self._writer.write_line(
                    f"rpc {method_name}({request_message}) returns ({response_message}) {{}}"
                )
        self._writer.write_line("}")
        self._writer.write_line("")

    def construct_method_message(self, message_info, model):
        """
        transform a message_info of type {is_stream: <boolean>, message: <string>} to a rpc parameter or return value.

        return value example: "stream MyModelRetrieveRequest"
        """
        return f"{'stream ' if message_info.get('is_stream', False) else ''}{message_info.get('message', model.__name__)}"

    def get_default_grpc_methods(self, model):
        """
        return the default grpc methods generated for a django model.
        """
        return {
            **ListModelMixin.get_default_method(model.__name__),
            **CreateModelMixin.get_default_method(model.__name__),
            **RetrieveModelMixin.get_default_method(model.__name__),
            **UpdateModelMixin.get_default_method(model.__name__),
            **DestroyModelMixin.get_default_method(model.__name__),
        }

    def get_default_grpc_messages(self, model):
        """
        return the default protobuff message we want to generate
        """
        return {
            **CreateModelMixin.get_default_message(model.__name__, "*"),
            **ListModelMixin.get_default_message(model.__name__),
            **RetrieveModelMixin.get_default_message(model.__name__, [model._meta.pk.name]),
            **DestroyModelMixin.get_default_message(model.__name__, [model._meta.pk.name]),
        }

    def _generate_message(self, model):
        grpc_messages = (
            model._meta.grpc_messages
            if hasattr(model, "_meta") and hasattr(model._meta, "grpc_messages")
            else self.get_default_grpc_messages(model)
        )

        if not grpc_messages:
            return

        for grpc_message_name, grpc_message_fields_name in grpc_messages.items():
            # We support the possibility to use "*" as parameter for fields
            if grpc_message_fields_name == "*":
                grpc_message_fields_name = [
                    field_info.name for field_info in get_model_fields(model)
                ]

            # Write the name of the message
            self._writer.write_line(f"message {grpc_message_name} {{")
            with self._writer.indent():
                number = 0
                # Write all fields as defined in the meta of the model
                for field_name in grpc_message_fields_name:
                    number += 1
                    field_info = model._meta.get_field(field_name)
                    self._writer.write_line(
                        f"{self.type_mapping.get(field_info.get_internal_type(), 'string')} {field_info.name} = {number};"
                    )
            self._writer.write_line("}")
            self._writer.write_line("")


class _CodeWriter:
    def __init__(self):
        self.buffer = io.StringIO()
        self._indent = 0

    def indent(self):
        return self

    def __enter__(self):
        self._indent += 1
        return self

    def __exit__(self, *args):
        self._indent -= 1

    def write_line(self, line):
        for i in range(self._indent):
            self.buffer.write("    ")
        print(line, file=self.buffer)

    def get_code(self):
        return self.buffer.getvalue()
