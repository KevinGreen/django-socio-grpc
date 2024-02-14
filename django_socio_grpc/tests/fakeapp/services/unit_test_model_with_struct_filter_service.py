from django_filters.rest_framework import DjangoFilterBackend
from fakeapp.models import UnitTestModel
from fakeapp.serializers import UnitTestModelWithStructFilterSerializer
from google.protobuf import empty_pb2
from rest_framework.pagination import PageNumberPagination

from django_socio_grpc import generics, mixins
from django_socio_grpc.decorators import grpc_action


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 3
    page_size_query_param = "page_size"
    max_page_size = 100


class UnitTestModelWithStructFilterService(
    generics.AsyncModelService, mixins.AsyncStreamModelMixin
):
    queryset = UnitTestModel.objects.all().order_by("id")
    serializer_class = UnitTestModelWithStructFilterSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["title", "text"]
    use_struct_filter_request = True
    use_struct_pagination_request = True

    @grpc_action(
        request=[],
        response="google.protobuf.Empty",
    )
    async def EmptyWithFilter(self, request, context):
        return empty_pb2.Empty()
