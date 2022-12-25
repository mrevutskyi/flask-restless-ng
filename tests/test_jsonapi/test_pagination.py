import pytest

from flask_restless import APIManager

from ..conftest import BaseTestClass
from .models import Base
from .models import Person


class TestPagination(BaseTestClass):
    """Tests for pagination links in fetched documents.

    For more information, see the `Pagination`_ section of the JSON API
    specification.

    .. _Pagination: https://jsonapi.org/format/#fetching-pagination

    """

    @pytest.fixture(autouse=True)
    def setup(self):
        manager = APIManager(self.app, session=self.session)
        manager.create_api(Person)
        self.manager = manager

        Base.metadata.create_all(bind=self.engine)
        yield
        Base.metadata.drop_all(bind=self.engine)

    def test_top_level_pagination_link(self):
        """Tests that there are top-level pagination links by default.

        For more information, see the `Top Level`_ section of the JSON
        API specification.

        .. _Top Level: https://jsonapi.org/format/#document-top-level

        """
        document = self.fetch_and_validate('/api/person')
        links = document['links']
        assert 'first' in links
        assert 'last' in links
        assert 'prev' in links
        assert 'next' in links

    def test_no_client_parameters(self):
        """Tests that a request without pagination query parameters returns the
        first page of the collection.

        For more information, see the `Pagination`_ section of the JSON API
        specification.

        .. _Pagination: https://jsonapi.org/format/#fetching-pagination

        """
        self.session.bulk_save_objects([Person(pk=i) for i in range(25)])
        self.session.commit()
        document = self.fetch_and_validate('/api/person', headers={'test-header': 'ok'})
        pagination = document['links']
        assert '/api/person?' in pagination['first']
        assert 'page[number]=1' in pagination['first']
        assert '/api/person?' in pagination['last']
        assert 'page[number]=3' in pagination['last']
        assert pagination['prev'] is None
        assert '/api/person?' in pagination['next']
        assert 'page[number]=2' in pagination['next']
        assert len(document['data']) == 10

    def test_x_forward_headers(self):
        self.session.bulk_save_objects([Person(pk=i) for i in range(25)])
        self.session.commit()
        document = self.fetch_and_validate('/api/person', headers={'X-Forwarded-Host': 'some-domain.net', 'X-Forwarded-Proto': 'https'})
        pagination = document['links']
        assert pagination['first'] == 'https://some-domain.net/api/person?page[size]=10&page[number]=1'

    def test_client_page_and_size(self):
        """Tests that a request that specifies both page number and page size
        returns the correct page of the collection.

        For more information, see the `Pagination`_ section of the JSON API
        specification.

        .. _Pagination: https://jsonapi.org/format/#fetching-pagination

        """
        self.session.bulk_save_objects([Person(pk=i) for i in range(25)])
        self.session.commit()
        query_string = {'page[number]': 2, 'page[size]': 3}
        document = self.fetch_and_validate('/api/person', query_string=query_string)
        pagination = document['links']
        assert '/api/person?' in pagination['first']
        assert 'page[number]=1' in pagination['first']
        assert '/api/person?' in pagination['last']
        assert 'page[number]=9' in pagination['last']
        assert '/api/person?' in pagination['prev']
        assert 'page[number]=1' in pagination['prev']
        assert '/api/person?' in pagination['next']
        assert 'page[number]=3' in pagination['next']
        assert len(document['data']) == 3

    def test_client_number_only(self):
        """Tests that a request that specifies only the page number returns the
        correct page with the default page size.

        For more information, see the `Pagination`_ section of the JSON API
        specification.

        .. _Pagination: https://jsonapi.org/format/#fetching-pagination

        """
        self.session.bulk_save_objects([Person(pk=i) for i in range(25)])
        self.session.commit()
        query_string = {'page[number]': 2}
        document = self.fetch_and_validate('/api/person', query_string=query_string)
        pagination = document['links']
        assert '/api/person?' in pagination['first']
        assert 'page[number]=1' in pagination['first']
        assert '/api/person?' in pagination['last']
        assert 'page[number]=3' in pagination['last']
        assert '/api/person?' in pagination['prev']
        assert 'page[number]=1' in pagination['prev']
        assert '/api/person?' in pagination['next']
        assert 'page[number]=3' in pagination['next']
        assert len(document['data']) == 10

    def test_sorted_pagination(self):
        """Tests that pagination is consistent with sorting.

        For more information, see the `Pagination`_ section of the JSON API
        specification.

        .. _Pagination: https://jsonapi.org/format/#fetching-pagination

        """
        self.session.bulk_save_objects([Person(pk=i) for i in range(1, 41)])
        self.session.commit()
        query_string = {'sort': '-pk', 'page[number]': 2}
        document = self.fetch_and_validate('/api/person', query_string=query_string)
        # In reverse order, the first page should have Person instances with
        # IDs 40 through 31, so the second page should have Person instances
        # with IDs 30 through 21.
        people = document['data']
        assert list(range(30, 20, -1)) == [int(p['id']) for p in people]
        # The pagination links should include not only the pagination query
        # parameters, but also the same sorting query parameters from the
        # client's original quest.
        pagination = document['links']
        assert '/api/person?' in pagination['first']
        assert 'page[number]=1' in pagination['first']
        assert 'sort=-pk' in pagination['first']

        assert '/api/person?' in pagination['last']
        assert 'page[number]=4' in pagination['last']
        assert 'sort=-pk' in pagination['last']

        assert '/api/person?' in pagination['prev']
        assert 'page[number]=1' in pagination['prev']
        assert 'sort=-pk' in pagination['prev']

        assert '/api/person?' in pagination['next']
        assert 'page[number]=3' in pagination['next']
        assert 'sort=-pk' in pagination['next']

    def test_client_size_only(self):
        """Tests that a request that specifies only the page size returns the
        first page with the requested page size.

        For more information, see the `Pagination`_ section of the JSON API
        specification.

        .. _Pagination: https://jsonapi.org/format/#fetching-pagination

        """
        self.session.bulk_save_objects([Person() for _ in range(25)])
        self.session.commit()
        query_string = {'page[size]': 5}
        document = self.fetch_and_validate('/api/person', query_string=query_string)
        pagination = document['links']
        assert '/api/person?' in pagination['first']
        assert 'page[number]=1' in pagination['first']
        assert '/api/person?' in pagination['last']
        assert 'page[number]=5' in pagination['last']
        assert pagination['prev'] is None
        assert '/api/person?' in pagination['next']
        assert 'page[number]=2' in pagination['next']
        assert len(document['data']) == 5

    def test_short_page(self):
        """Tests that a request that specifies the last page may get fewer
        resources than the page size.

        For more information, see the `Pagination`_ section of the JSON API
        specification.

        .. _Pagination: https://jsonapi.org/format/#fetching-pagination

        """
        self.session.bulk_save_objects([Person() for _ in range(25)])
        self.session.commit()
        document = self.fetch_and_validate('/api/person', query_string={'page[number]': 3})
        pagination = document['links']
        assert '/api/person?' in pagination['first']
        assert 'page[number]=1' in pagination['first']
        assert '/api/person?' in pagination['last']
        assert 'page[number]=3' in pagination['last']
        assert '/api/person?' in pagination['prev']
        assert 'page[number]=2' in pagination['prev']
        assert pagination['next'] is None
        assert len(document['data']) == 5

    def test_server_page_size(self):
        """Tests for setting the default page size on the server side.

        For more information, see the `Pagination`_ section of the JSON API
        specification.

        .. _Pagination: https://jsonapi.org/format/#fetching-pagination

        """
        self.session.bulk_save_objects([Person() for _ in range(25)])
        self.session.commit()
        self.manager.create_api(Person, url_prefix='/api2', page_size=5)
        query_string = {'page[number]': 3}
        document = self.fetch_and_validate('/api2/person', query_string=query_string)
        pagination = document['links']
        assert '/api2/person?' in pagination['first']
        assert 'page[number]=1' in pagination['first']
        assert '/api2/person?' in pagination['last']
        assert 'page[number]=5' in pagination['last']
        assert '/api2/person?' in pagination['prev']
        assert 'page[number]=2' in pagination['prev']
        assert '/api2/person?' in pagination['next']
        assert 'page[number]=4' in pagination['next']
        assert len(document['data']) == 5

    def test_disable_pagination(self):
        """Tests for disabling default pagination on the server side.

        For more information, see the `Pagination`_ section of the JSON API
        specification.

        .. _Pagination: https://jsonapi.org/format/#fetching-pagination

        """
        self.session.bulk_save_objects([Person() for _ in range(25)])
        self.session.commit()
        self.manager.create_api(Person, url_prefix='/api2', page_size=0)
        document = self.fetch_and_validate('/api2/person')
        pagination = document['links']
        assert 'first' not in pagination
        assert 'last' not in pagination
        assert 'prev' not in pagination
        assert 'next' not in pagination
        assert len(document['data']) == 25

    def test_disable_pagination_raiser_client_error(self):
        """Tests that disabling default pagination on the server raises an error on client page number requests."""
        self.session.bulk_save_objects([Person() for _ in range(25)])
        self.session.commit()
        self.manager.create_api(Person, url_prefix='/api2', page_size=0)
        query_string = {'page[number]': 2}
        self.fetch_and_validate('/api2/person', query_string=query_string, expected_response_code=400,
                                error_msg='Page number can not be used with with page size 0')

    def test_max_page_size(self):
        """Tests that the client cannot exceed the maximum page size.

        For more information, see the `Pagination`_ section of the JSON API
        specification.

        .. _Pagination: https://jsonapi.org/format/#fetching-pagination

        """
        self.session.bulk_save_objects([Person() for _ in range(25)])
        self.session.commit()
        self.manager.create_api(Person, url_prefix='/api2', max_page_size=15)
        query_string = {'page[size]': 20}
        self.fetch_and_validate('/api2/person', query_string=query_string, expected_response_code=400,
                                error_msg="Page size must not exceed the server's maximum")

    def test_negative_page_size(self):
        """Tests that the client cannot specify a negative page size.

        For more information, see the `Pagination`_ section of the JSON API
        specification.

        .. _Pagination: https://jsonapi.org/format/#fetching-pagination

        """
        query_string = {'page[size]': -1}
        self.fetch_and_validate('/api/person', query_string=query_string, expected_response_code=400,
                                error_msg='Page size can not be negative')

    def test_negative_page_number(self):
        """Tests that the client cannot specify a negative page number.

        For more information, see the `Pagination`_ section of the JSON API
        specification.

        .. _Pagination: https://jsonapi.org/format/#fetching-pagination

        """
        query_string = {'page[number]': -1}
        self.fetch_and_validate('/api/person', query_string=query_string, expected_response_code=400,
                                error_msg='Page number can not be negative')

    def test_headers(self):
        """Tests that paginated requests come with ``Link`` headers.

        (This is not part of the JSON API standard, but should live with the
        other pagination test methods anyway.)

        """
        self.session.bulk_save_objects([Person() for _ in range(25)])
        self.session.commit()
        query_string = {'page[number]': 4, 'page[size]': 3}
        response = self.client.get('/api/person', query_string=query_string)
        links = response.headers['Link'].split(',')
        assert any(all(('/api/person?' in link, 'page[number]=1' in link,
                        'page[size]=3' in link, 'rel="first"' in link))
                   for link in links)
        assert any(all(('/api/person?' in link, 'page[number]=9' in link,
                        'page[size]=3' in link, 'rel="last"' in link))
                   for link in links)
        assert any(all(('/api/person?' in link, 'page[number]=3' in link,
                        'page[size]=3' in link, 'rel="prev"' in link))
                   for link in links)
        assert any(all(('/api/person?' in link, 'page[number]=5' in link,
                        'page[size]=3' in link, 'rel="next"' in link))
                   for link in links)
