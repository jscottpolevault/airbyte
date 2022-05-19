#
# Copyright (c) 2021 Airbyte, Inc., all rights reserved.
#


from abc import ABC
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

import requests
from airbyte_cdk import AirbyteLogger
from airbyte_cdk.models import SyncMode
from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream
from airbyte_cdk.sources.streams.http import HttpStream
from airbyte_cdk.sources.streams.http.auth import Oauth2Authenticator, TokenAuthenticator


class LinkedinPagesStream(HttpStream, ABC):

    url_base = "https://api.linkedin.com/v2/"
    primary_key = None

    def __init__(self, config):
        super().__init__(authenticator=config.get("authenticator"))
        self.config = config
        

    @property
    def org(self):
        """Property to return the user Organization Id from input"""
        return self.config.get("org_id")
        
    def path(self, **kwargs) -> str:
        """Returns the API endpoint path for stream, from `endpoint` class attribute."""
        return self.endpoint

    def next_page_token(self, response: requests.Response) -> Optional[Mapping[str, Any]]:
        return None

    def parse_response(
        self,
        response: requests.Response,
        stream_state: Mapping[str, Any] = None,
        stream_slice: Mapping[str, Any] = None
    ) -> Iterable[Mapping]:
        return [response.json()]

class OrganizationLookup(LinkedinPagesStream):

    def path(self, stream_state: Mapping[str, Any], **kwargs) -> MutableMapping[str, Any]:
    
        path = f"organizations/{self.org}"
        return path

class FollowerStatistics(LinkedinPagesStream):

    def path(self, stream_state: Mapping[str, Any], **kwargs) -> MutableMapping[str, Any]:
    
        path = f"organizationalEntityFollowerStatistics?q=organizationalEntity&organizationalEntity=urn:li:organization:{self.org}"
        return path

class PageStatistics(LinkedinPagesStream):

    def path(self, stream_state: Mapping[str, Any], **kwargs) -> MutableMapping[str, Any]:
    
        path = f"organizationPageStatistics?q=organization&organization=urn%3Ali%3Aorganization%3A{self.org}"
        return path

class ShareStatistics(LinkedinPagesStream):

    def path(self, stream_state: Mapping[str, Any], **kwargs) -> MutableMapping[str, Any]:
    
        path = f"organizationalEntityShareStatistics?q=organizationalEntity&organizationalEntity=urn%3Ali%3Aorganization%3A{self.org}"
        return path

class Shares(LinkedinPagesStream):

    def path(self, stream_state: Mapping[str, Any], **kwargs) -> MutableMapping[str, Any]:
    
        path = f"shares?q=owners&owners=urn%3Ali%3Aorganization%3A{self.org}&sortBy=LAST_MODIFIED&sharesPerOwner=50"
        return path

class TotalFollowerCount(LinkedinPagesStream):

    def path(self, stream_state: Mapping[str, Any], **kwargs) -> MutableMapping[str, Any]:
    
        path = f"networkSizes/urn:li:organization:{self.org}?edgeType=CompanyFollowedByMember"
        return path
    
class UgcPosts(LinkedinPagesStream):

    def path(self, stream_state: Mapping[str, Any], **kwargs) -> MutableMapping[str, Any]:
    
        path = f"ugcPosts?q=authors&authors=List(urn%3Ali%3Aorganization%3A{self.org})&sortBy=LAST_MODIFIED&count=50"
        return path

    def request_headers(self, stream_state: Mapping[str, Any], **kwargs) -> Mapping[str, Any]:
        """
        If org_ids are specified as user's input from configuration,
        we must use MODIFIED header: {'X-RestLi-Protocol-Version': '2.0.0'}
        """
        return {"X-RestLi-Protocol-Version": "2.0.0"} if self.org else {}


class SourceLinkedinPages(AbstractSource):
    """
    Abstract Source inheritance, provides:
    - implementation for `check` connector's connectivity
    - implementation to call each stream with it's input parameters.
    """

    @classmethod
    def get_authenticator(cls, config: Mapping[str, Any]) -> TokenAuthenticator:
        """
        Validate input parameters and generate a necessary Authentication object
        This connectors support 2 auth methods:
        1) direct access token with TTL = 2 months
        2) refresh token (TTL = 1 year) which can be converted to access tokens
           Every new refresh revokes all previous access tokens q
        """
        auth_method = config.get("credentials", {}).get("auth_method")
        if not auth_method or auth_method == "access_token":
            # support of backward compatibility with old exists configs
            access_token = config["credentials"]["access_token"] if auth_method else config["access_token"]
            return TokenAuthenticator(token=access_token)
        elif auth_method == "oAuth2.0":
            return Oauth2Authenticator(
                token_refresh_endpoint="https://www.linkedin.com/oauth/v2/accessToken",
                client_id=config["credentials"]["client_id"],
                client_secret=config["credentials"]["client_secret"],
                refresh_token=config["credentials"]["refresh_token"],
            )
        raise Exception("incorrect input parameters")

    def check_connection(self, logger: AirbyteLogger, config: Mapping[str, Any]) -> Tuple[bool, any]:
        # RUN $ python main.py check --config secrets/config.json

        """
        Testing connection availability for the connector.
        :: for this check method the Customer must have the "r_liteprofile" scope enabled.
        :: more info: https://docs.microsoft.com/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin
        """

        config["authenticator"] = self.get_authenticator(config)
        stream = OrganizationLookup(config)
        stream.records_limit = 1
        try:
            next(stream.read_records(sync_mode=SyncMode.full_refresh), None)
            return True, None
        except Exception as e:
            return False, e
        
        # RUN: $ python main.py read --config secrets/config.json --catalog integration_tests/configured_catalog.json

    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        config["authenticator"] = self.get_authenticator(config)
        return [
            OrganizationLookup(config),
            FollowerStatistics(config),
            PageStatistics(config),
            ShareStatistics(config),
            Shares(config),
            TotalFollowerCount(config),
            UgcPosts(config)
        ]
        
