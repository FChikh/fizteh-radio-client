import json
import mimetypes
import os
from time import time
import jwt
import music_tag
from pytz import timezone
import requests
from data_types import Tag, Media, Segment, TagType, Live
from datetime import datetime, timedelta
# Constants

# Custom Exceptions


class APIClientError(Exception):
    """Base exception for APIClient."""
    pass


class AuthenticationError(APIClientError):
    """Raised when authentication fails."""
    pass


class AuthorizationError(APIClientError):
    """Raised when the user is not authorized to perform an action."""
    pass


class NotFoundError(APIClientError):
    """Raised when a requested resource is not found."""
    pass


class ServerError(APIClientError):
    """Raised when the server encounters an error."""
    pass


class ValidationError(APIClientError):
    """Raised when input data is invalid."""
    pass


def is_valid_file(arg):
    if not os.path.exists(arg):
        raise FileNotFoundError(f"The file {arg} does not exist!")
    else:
        # Guess the MIME type of the file
        type_guess, _ = mimetypes.guess_type(arg)
        if type_guess != 'audio/mpeg':
            raise TypeError(
                f"The file {arg} is not an MP3 file based on MIME type guessing.")
    return arg


def extract_metadata_and_remove_artwork(file_path):
    f = music_tag.load_file(file_path)

    # Extract author and track name
    author = f['artist']
    track_name = f['title']

    # Check and delete cover artwork if exists
    if f['artwork']:
        del f['artwork']
        f.save()

    return {
        "author": str(author),
        "name": str(track_name)
    }


class client:
    base_url = 'https://radiomipt.ru'

    def __init__(self, token: str = None) -> None:
        self.cache_dir = '.cache'
        os.makedirs(self.cache_dir, exist_ok=True)
        self.jwt = None
        self.auth_header = None
        if token:
            self.set_token(token)
        self.user_info = self.__recover_user_info()
        self.library = {}
        self.schedule = []
        self.time_horizon = None

    def set_token(self, token: str) -> None:
        self.__add_token(token)
        self.auth_header = {'Authorization': f'Bearer {self.jwt.token}'}

    def __add_token(self, token: str) -> None:
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            # Default to 1 hour if 'exp' not present
            timeout = payload.get('exp', time() + 3600)
            self.jwt = JWT(token, timeout)
        except jwt.DecodeError as e:
            raise AuthenticationError("Invalid JWT token.") from e

    def __refresh_jwt_if_needed(self) -> None:
        if not self.jwt or self.jwt.is_expired():
            if self.user_info:
                success = self.login(
                    self.user_info['login'], self.user_info['pass'])
                if not success:
                    raise AuthenticationError("Failed to refresh JWT token.")
            else:
                raise AuthenticationError(
                    "User information not available for token refresh.")

    def __recover_user_info(self) -> dict:
        try:
            with open(os.path.join(self.cache_dir, 'users.json'), 'r') as r:
                return json.load(r)
        except FileNotFoundError:
            return {}
        except Exception as e:
            print(f"Exception when recovering user info: {e}")
            raise APIClientError("Failed to recover user information.") from e

    def __save_user(self, login: str, password: str) -> None:
        self.user_info = {'login': login, 'pass': password}
        try:
            with open(os.path.join(self.cache_dir, 'users.json'), 'w') as wr:
                json.dump(self.user_info, wr)
        except Exception as e:
            print(f"Exception when saving user info: {e}")
            raise APIClientError("Failed to save user information.") from e

    def login(self, login: str, password: str) -> bool:
        url = f'{self.base_url}/admin/login'
        data = {'login': login, 'pass': password}

        try:
            api_response = requests.post(url, json=data)
            api_response.raise_for_status()
            token = api_response.json().get('token')
            if not token:
                raise AuthenticationError("Token not found in response.")
            self.__add_token(token)
            self.auth_header = {'Authorization': f'Bearer {self.jwt.token}'}
            self.__save_user(login, password)
            return True
        except requests.HTTPError as http_err:
            if api_response.status_code == 401:
                raise AuthenticationError("Invalid credentials.") from http_err
            elif api_response.status_code == 403:
                raise AuthorizationError("Forbidden access.") from http_err
            else:
                raise APIClientError(
                    f"HTTP error occurred: {http_err}") from http_err
        except Exception as e:
            print(f"Exception during login: {e}")
            raise APIClientError("An error occurred during login.") from e

    # Media Handling

    def fetch_all_media(self) -> list[Media]:
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/library/media'
        try:
            response = requests.get(url, headers=self.auth_header)
            response.raise_for_status()
            media_list = response.json().get('library', [])
            self.library = {int(item['id']): Media.from_dict(item)
                            for item in media_list}
            return list(self.library.values())
        except requests.HTTPError as http_err:
            if response.status_code == 404:
                raise NotFoundError("Media library not found.") from http_err
            elif response.status_code >= 500:
                raise ServerError(
                    "Server error while fetching media.") from http_err
            else:
                raise APIClientError(
                    f"HTTP error occurred: {http_err}") from http_err
        except Exception as e:
            print(f"Exception during fetch_all_media: {e}")
            raise APIClientError(
                "An error occurred while fetching all media.") from e

    def search_media_in_library(self, name: str = None, author: str = None, tags: list = None, res_len: int = 5) -> list[Media]:
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/library/media'
        params = {'res_len': res_len}
        if name:
            params['name'] = name
        if author:
            params['author'] = author
        if tags:
            params['tags'] = tags  # Ensure tags are serialized appropriately

        try:
            response = requests.get(
                url, headers=self.auth_header, params=params)
            response.raise_for_status()
            media_list = response.json().get('library', [])
            return [Media.from_dict(item) for item in media_list]
        except requests.HTTPError as http_err:
            if response.status_code == 404:
                raise NotFoundError("Media not found.") from http_err
            elif response.status_code >= 500:
                raise ServerError(
                    "Server error while searching media.") from http_err
            else:
                raise APIClientError(
                    f"HTTP error occurred: {http_err}") from http_err
        except Exception as e:
            print(f"Exception during search_media_in_library: {e}")
            raise APIClientError(
                "An error occurred while searching media.") from e

    def get_media(self, media_id: int) -> Media:
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/library/media/{media_id}'
        try:
            response = requests.get(url, headers=self.auth_header)
            response.raise_for_status()
            media_data = response.json().get('media')
            if not media_data:
                raise NotFoundError(f"Media with ID {media_id} not found.")
            return Media.from_dict(media_data)
        except requests.HTTPError as http_err:
            if response.status_code == 404:
                raise NotFoundError(
                    f"Media with ID {media_id} not found.") from http_err
            elif response.status_code >= 500:
                raise ServerError(
                    "Server error while retrieving media.") from http_err
            else:
                raise APIClientError(
                    f"HTTP error occurred: {http_err}") from http_err
        except Exception as e:
            print(f"Exception during get_media: {e}")
            raise APIClientError(
                "An error occurred while retrieving media.") from e

    def post_media_with_source(self, name: str, author: str, source: str, tags: list) -> int:
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/library/media'
        media = Media(name=name, author=author, tags=tags)
        try:
            is_valid_file(source)
            metadata = extract_metadata_and_remove_artwork(source)
        except (FileNotFoundError, TypeError) as e:
            print(f"File validation error: {e}")
            raise ValidationError(str(e)) from e

        files = {
            'source': (os.path.basename(source), open(source, 'rb'), 'audio/mpeg'),
            'media': (None, json.dumps(media.to_dict()), 'application/json')
        }

        try:
            response = requests.post(
                url, headers=self.auth_header, files=files)
            response.raise_for_status()
            media_id = response.json().get('id')
            if media_id is None:
                raise APIClientError("Media ID not returned in response.")
            return media_id
        except requests.HTTPError as http_err:
            if response.status_code == 400:
                error_msg = response.json().get('error', 'Bad Request')
                if error_msg == 'segment intersection':
                    raise ValidationError(
                        "Segment intersection error.") from http_err
                else:
                    raise ValidationError(error_msg) from http_err
            elif response.status_code >= 500:
                raise ServerError(
                    "Server error while uploading media.") from http_err
            else:
                raise APIClientError(
                    f"HTTP error occurred: {http_err}") from http_err
        except Exception as e:
            print(f"Exception during post_media_with_source: {e}")
            raise APIClientError(
                "An error occurred while uploading media.") from e
        finally:
            # Ensure the file is closed
            files['source'][1].close()

    def update_media_information(self, media_id: int, name: str, author: str, tags: list[Tag]) -> Media:
        self.__refresh_jwt_if_needed()
        media = Media(id=media_id, name=name, author=author, tags=tags)
        url = f'{self.base_url}/admin/library/media/{media_id}'
        payload = {'media': media.to_dict()}

        try:
            response = requests.put(
                url, headers=self.auth_header, json=payload)
            response.raise_for_status()
            updated_media = response.json().get('media')
            if not updated_media:
                raise APIClientError("Updated media data not returned.")
            return Media.from_dict(updated_media)
        except requests.HTTPError as http_err:
            if response.status_code == 404:
                raise NotFoundError(
                    f"Media with ID {media_id} not found.") from http_err
            elif response.status_code == 400:
                error_msg = response.json().get('error', 'Bad Request')
                raise ValidationError(error_msg) from http_err
            elif response.status_code >= 500:
                raise ServerError(
                    "Server error while updating media.") from http_err
            else:
                raise APIClientError(
                    f"HTTP error occurred: {http_err}") from http_err
        except Exception as e:
            print(f"Exception during update_media_information: {e}")
            raise APIClientError(
                "An error occurred while updating media information.") from e

    def delete_media_by_id(self, media_id: int) -> None:
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/library/media/{media_id}'
        try:
            response = requests.delete(url, headers=self.auth_header)
            response.raise_for_status()
        except requests.HTTPError as http_err:
            if response.status_code == 404:
                raise NotFoundError(
                    f"Media with ID {media_id} not found.") from http_err
            elif response.status_code >= 500:
                raise ServerError(
                    "Server error while deleting media.") from http_err
            else:
                raise APIClientError(
                    f"HTTP error occurred: {http_err}") from http_err
        except Exception as e:
            print(f"Exception during delete_media_by_id: {e}")
            raise APIClientError(
                "An error occurred while deleting media.") from e

    # Tag Handling

    def get_available_tag_types(self) -> list[TagType]:
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/library/tag/types'
        try:
            response = requests.get(url, headers=self.auth_header)
            response.raise_for_status()
            types = response.json().get('types', [])
            return [TagType.from_dict(item) for item in types]
        except requests.HTTPError as http_err:
            if response.status_code == 404:
                raise NotFoundError("Tag types not found.") from http_err
            elif response.status_code >= 500:
                raise ServerError(
                    "Server error while fetching tag types.") from http_err
            else:
                raise APIClientError(
                    f"HTTP error occurred: {http_err}") from http_err
        except Exception as e:
            print(f"Exception during get_available_tag_types: {e}")
            raise APIClientError(
                "An error occurred while fetching tag types.") from e

    def get_all_registered_tags(self) -> list[Tag]:
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/library/tag'
        try:
            response = requests.get(url, headers=self.auth_header)
            response.raise_for_status()
            tags = response.json().get('tags', [])
            return [Tag.from_dict(item) for item in tags]
        except requests.HTTPError as http_err:
            if response.status_code == 404:
                raise NotFoundError("Tags not found.") from http_err
            elif response.status_code >= 500:
                raise ServerError(
                    "Server error while fetching tags.") from http_err
            else:
                raise APIClientError(
                    f"HTTP error occurred: {http_err}") from http_err
        except Exception as e:
            print(f"Exception during get_all_registered_tags: {e}")
            raise APIClientError(
                "An error occurred while fetching tags.") from e

    def register_new_tag(self, tag_name: str, tag_type: dict, meta: dict = {}) -> int:
        self.__refresh_jwt_if_needed()
        tag_type_obj = TagType(id=tag_type['id'], name=tag_type['name'])
        tag = Tag(name=tag_name, type=tag_type_obj, meta=meta)
        url = f'{self.base_url}/admin/library/tag'
        payload = {'tag': tag.to_dict()}

        try:
            response = requests.post(
                url, headers=self.auth_header, json=payload)
            response.raise_for_status()
            tag_id = response.json().get('id')
            if tag_id is None:
                raise APIClientError("Tag ID not returned in response.")
            return tag_id
        except requests.HTTPError as http_err:
            if response.status_code == 400:
                error_msg = response.json().get('error', 'Bad Request')
                raise ValidationError(error_msg) from http_err
            elif response.status_code >= 500:
                raise ServerError(
                    "Server error while registering new tag.") from http_err
            else:
                raise APIClientError(
                    f"HTTP error occurred: {http_err}") from http_err
        except Exception as e:
            print(f"Exception during register_new_tag: {e}")
            raise APIClientError(
                "An error occurred while registering new tag.") from e

    def update_tag(self, tag_id: int, tag_name: str, tag_type: dict, meta: dict = {}) -> Tag:
        self.__refresh_jwt_if_needed()
        tag_type_obj = TagType(id=tag_type['id'], name=tag_type['name'])
        tag = Tag(id=tag_id, name=tag_name, type=tag_type_obj, meta=meta)
        url = f'{self.base_url}/admin/library/tag'
        payload = {'tag': tag.to_dict()}

        try:
            response = requests.put(
                url, headers=self.auth_header, json=payload)
            response.raise_for_status()
            updated_tag = response.json().get('tag')
            if not updated_tag:
                raise APIClientError("Updated tag data not returned.")
            return Tag.from_dict(updated_tag)
        except requests.HTTPError as http_err:
            if response.status_code == 404:
                raise NotFoundError(
                    f"Tag with ID {tag_id} not found.") from http_err
            elif response.status_code == 400:
                error_msg = response.json().get('error', 'Bad Request')
                raise ValidationError(error_msg) from http_err
            elif response.status_code >= 500:
                raise ServerError(
                    "Server error while updating tag.") from http_err
            else:
                raise APIClientError(
                    f"HTTP error occurred: {http_err}") from http_err
        except Exception as e:
            print(f"Exception during update_tag: {e}")
            raise APIClientError(
                "An error occurred while updating tag.") from e

    def get_tag_by_id(self, tag_id: int) -> Tag:
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/library/tag/{tag_id}'
        try:
            response = requests.get(url, headers=self.auth_header)
            response.raise_for_status()
            tag_data = response.json().get('tag')
            if not tag_data:
                raise NotFoundError(f"Tag with ID {tag_id} not found.")
            return Tag.from_dict(tag_data)
        except requests.HTTPError as http_err:
            if response.status_code == 404:
                raise NotFoundError(
                    f"Tag with ID {tag_id} not found.") from http_err
            elif response.status_code >= 500:
                raise ServerError(
                    "Server error while retrieving tag.") from http_err
            else:
                raise APIClientError(
                    f"HTTP error occurred: {http_err}") from http_err
        except Exception as e:
            print(f"Exception during get_tag_by_id: {e}")
            raise APIClientError(
                "An error occurred while retrieving tag.") from e

    def delete_tag_by_id(self, tag_id: int) -> None:
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/library/tag/{tag_id}'
        try:
            response = requests.delete(url, headers=self.auth_header)
            response.raise_for_status()
        except requests.HTTPError as http_err:
            if response.status_code == 404:
                raise NotFoundError(
                    f"Tag with ID {tag_id} not found.") from http_err
            elif response.status_code >= 500:
                raise ServerError(
                    "Server error while deleting tag.") from http_err
            else:
                raise APIClientError(
                    f"HTTP error occurred: {http_err}") from http_err
        except Exception as e:
            print(f"Exception during delete_tag_by_id: {e}")
            raise APIClientError(
                "An error occurred while deleting tag.") from e

    # Schedule and Segment Management

    def get_schedule(self, start: datetime = None, stop: datetime = None) -> list[Segment]:
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/schedule'
        params = {}
        if start:
            params['start'] = start.strftime('%s')
        else:
            params['start'] = datetime.now().strftime('%s')
        if stop:
            params['stop'] = stop.strftime('%s')

        try:
            response = requests.get(
                url, headers=self.auth_header, params=params)
            response.raise_for_status()
            segments = response.json().get('segments', [])
            self.schedule = segments

            if segments:
                last_segment = segments[-1]
                try:
                    start_time = datetime.strptime(
                        last_segment['start'], r'%Y-%m-%dT%H:%M:%S.%f%z')
                except ValueError:
                    start_time = datetime.strptime(
                        last_segment['start'], r'%Y-%m-%dT%H:%M:%S%z')
                duration = timedelta(
                    microseconds=last_segment['stopCut'] * 1e-3)
                self.time_horizon = start_time + duration

                self.fetch_all_media()
                now = datetime.now(tz=timezone('UTC'))
                for item in self.schedule:
                    try:
                        segment_start = datetime.strptime(
                            item['start'], r'%Y-%m-%dT%H:%M:%S.%f%z')
                    except ValueError:
                        segment_start = datetime.strptime(
                            item['start'], r'%Y-%m-%dT%H:%M:%S%z')
                    duration = timedelta(microseconds=item['stopCut'] * 1e-3)
                    segment_end = segment_start + duration
                    item['end'] = segment_end.strftime(
                        r'%Y-%m-%dT%H:%M:%S.%f%z')
                    # Assign media title
                    media_id = int(item['mediaID'])
                    media = self.library.get(media_id)
                    if media:
                        item['mediaTitle'] = f"{media.author} - {media.name}"
                    else:
                        item['mediaTitle'] = "Unknown Media"

                # Filter out past segments
                self.schedule = [
                    item for item in self.schedule
                    if datetime.strptime(item['end'], r'%Y-%m-%dT%H:%M:%S.%f%z') > now
                ]
            return [Segment.from_dict(seg) for seg in self.schedule]
        except requests.HTTPError as http_err:
            if response.status_code == 404:
                raise NotFoundError("Schedule not found.") from http_err
            elif response.status_code >= 500:
                raise ServerError(
                    "Server error while fetching schedule.") from http_err
            else:
                raise APIClientError(
                    f"HTTP error occurred: {http_err}") from http_err
        except Exception as e:
            print(f"Exception during get_schedule: {e}")
            raise APIClientError(
                "An error occurred while fetching schedule.") from e

    def create_new_segment(self, media_id: int, *, time: datetime = None, stop_cut: int = None) -> int:
        self.__refresh_jwt_if_needed()
        self.get_schedule()

        now = datetime.now(tz=timezone('UTC'))
        if self.time_horizon is None or self.time_horizon < now:
            self.time_horizon = now

        media = self.get_media(media_id)
        if media is None:
            raise NotFoundError("Unknown media_id.")

        start = self.time_horizon if not time else time

        if stop_cut is None:
            stop_cut = media.duration

        segment = Segment(
            mediaID=media_id,
            start=start.strftime(r"%Y-%m-%dT%H:%M:%S.%f+00:00"),
            beginCut=0,
            stopCut=stop_cut
        )
        url = f'{self.base_url}/admin/schedule'
        payload = {'segment': segment.to_dict()}

        try:
            response = requests.post(
                url, headers=self.auth_header, json=payload)
            response.raise_for_status()
            segment_id = response.json().get('id')
            if segment_id is None:
                raise APIClientError("Segment ID not returned in response.")
            self.time_horizon = start + \
                timedelta(microseconds=media.duration * 1e3)
            return segment_id
        except requests.HTTPError as http_err:
            if response.status_code == 400:
                error_msg = response.json().get('error', 'Bad Request')
                if error_msg == 'segment intersection':
                    raise ValidationError(
                        "Segment intersection detected.") from http_err
                else:
                    raise ValidationError(error_msg) from http_err
            elif response.status_code >= 500:
                raise ServerError(
                    "Server error while creating new segment.") from http_err
            else:
                raise APIClientError(
                    f"HTTP error occurred: {http_err}") from http_err
        except Exception as e:
            print(f"Exception during create_new_segment: {e}")
            raise APIClientError(
                "An error occurred while creating a new segment.") from e

    def clear_schedule_from_timestamp(self, timestamp: datetime) -> None:
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/schedule'
        params = {'from': timestamp.strftime('%s')}

        try:
            response = requests.delete(
                url, headers=self.auth_header, params=params)
            response.raise_for_status()
        except requests.HTTPError as http_err:
            if response.status_code == 404:
                raise NotFoundError("Schedule not found.") from http_err
            elif response.status_code >= 500:
                raise ServerError(
                    "Server error while clearing schedule.") from http_err
            else:
                raise APIClientError(
                    f"HTTP error occurred: {http_err}") from http_err
        except Exception as e:
            print(f"Exception during clear_schedule_from_timestamp: {e}")
            raise APIClientError(
                "An error occurred while clearing schedule.") from e

    def get_segment_by_id(self, segment_id: int) -> Segment:
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/schedule/{segment_id}'
        try:
            response = requests.get(url, headers=self.auth_header)
            response.raise_for_status()
            segment_data = response.json().get('segment')
            if not segment_data:
                raise NotFoundError(f"Segment with ID {segment_id} not found.")
            segment_data.pop('protected', None)
            return Segment.from_dict(segment_data)
        except requests.HTTPError as http_err:
            if response.status_code == 404:
                raise NotFoundError(
                    f"Segment with ID {segment_id} not found.") from http_err
            elif response.status_code >= 500:
                raise ServerError(
                    "Server error while retrieving segment.") from http_err
            else:
                raise APIClientError(
                    f"HTTP error occurred: {http_err}") from http_err
        except Exception as e:
            print(f"Exception during get_segment_by_id: {e}")
            raise APIClientError(
                "An error occurred while retrieving segment.") from e

    def delete_segment_by_id(self, segment_id: int) -> None:
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/schedule/{segment_id}'
        try:
            response = requests.delete(url, headers=self.auth_header)
            response.raise_for_status()
        except requests.HTTPError as http_err:
            if response.status_code == 404:
                raise NotFoundError(
                    f"Segment with ID {segment_id} not found.") from http_err
            elif response.status_code >= 500:
                raise ServerError(
                    "Server error while deleting segment.") from http_err
            else:
                raise APIClientError(
                    f"HTTP error occurred: {http_err}") from http_err
        except Exception as e:
            print(f"Exception during delete_segment_by_id: {e}")
            raise APIClientError(
                "An error occurred while deleting segment.") from e

    # Radio Control

    def start_radio(self) -> None:
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/radio/start'
        try:
            response = requests.get(url, headers=self.auth_header)
            response.raise_for_status()
        except requests.HTTPError as http_err:
            if response.status_code == 403:
                raise AuthorizationError(
                    "Forbidden: Cannot start radio.") from http_err
            elif response.status_code >= 500:
                raise ServerError(
                    "Server error while starting radio.") from http_err
            else:
                raise APIClientError(
                    f"HTTP error occurred: {http_err}") from http_err
        except Exception as e:
            print(f"Exception during start_radio: {e}")
            raise APIClientError(
                "An error occurred while starting radio.") from e

    def stop_radio(self) -> None:
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/radio/stop'
        try:
            response = requests.get(url, headers=self.auth_header)
            response.raise_for_status()
        except requests.HTTPError as http_err:
            if response.status_code == 403:
                raise AuthorizationError(
                    "Forbidden: Cannot stop radio.") from http_err
            elif response.status_code >= 500:
                raise ServerError(
                    "Server error while stopping radio.") from http_err
            else:
                raise APIClientError(
                    f"HTTP error occurred: {http_err}") from http_err
        except Exception as e:
            print(f"Exception during stop_radio: {e}")
            raise APIClientError(
                "An error occurred while stopping radio.") from e

    # Live Control

    def start_live(self, name: str) -> None:
        self.__refresh_jwt_if_needed()
        live = Live(name=name)
        url = f'{self.base_url}/admin/schedule/live/start'
        payload = {'live': live.to_dict()}
        try:
            response = requests.post(
                url, headers=self.auth_header, json=payload)
            response.raise_for_status()
        except requests.HTTPError as http_err:
            if response.status_code == 400:
                error_msg = response.json().get('error', 'Bad Request')
                raise ValidationError(error_msg) from http_err
            elif response.status_code >= 500:
                raise ServerError(
                    "Server error while starting live.") from http_err
            else:
                raise APIClientError(
                    f"HTTP error occurred: {http_err}") from http_err
        except Exception as e:
            print(f"Exception during start_live: {e}")
            raise APIClientError(
                "An error occurred while starting live.") from e

    def stop_live(self) -> None:
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/schedule/live/stop'
        try:
            response = requests.get(url, headers=self.auth_header)
            response.raise_for_status()
        except requests.HTTPError as http_err:
            if response.status_code == 400:
                error_msg = response.json().get('error', 'Bad Request')
                raise ValidationError(error_msg) from http_err
            elif response.status_code >= 500:
                raise ServerError(
                    "Server error while stopping live.") from http_err
            else:
                raise APIClientError(
                    f"HTTP error occurred: {http_err}") from http_err
        except Exception as e:
            print(f"Exception during stop_live: {e}")
            raise APIClientError(
                "An error occurred while stopping live.") from e

    def get_live_status(self) -> dict:
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/schedule/live/info'
        try:
            response = requests.get(url, headers=self.auth_header)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as http_err:
            if response.status_code == 404:
                raise NotFoundError("Live status not found.") from http_err
            elif response.status_code >= 500:
                raise ServerError(
                    "Server error while fetching live status.") from http_err
            else:
                raise APIClientError(
                    f"HTTP error occurred: {http_err}") from http_err
        except Exception as e:
            print(f"Exception during get_live_status: {e}")
            raise APIClientError(
                "An error occurred while fetching live status.") from e

    def get_lives(self) -> list[Live]:
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/schedule/lives'
        try:
            response = requests.get(url, headers=self.auth_header)
            response.raise_for_status()
            lives = response.json().get('lives', [])
            return [Live.from_dict(item) for item in lives]
        except requests.HTTPError as http_err:
            if response.status_code == 404:
                raise NotFoundError("Lives not found.") from http_err
            elif response.status_code >= 500:
                raise ServerError(
                    "Server error while fetching lives.") from http_err
            else:
                raise APIClientError(
                    f"HTTP error occurred: {http_err}") from http_err
        except Exception as e:
            print(f"Exception during get_lives: {e}")
            raise APIClientError(
                "An error occurred while fetching lives.") from e


class JWT:
    def __init__(self, token: str, timeout: float) -> None:
        self.token = token
        self.timeout = timeout

    def is_expired(self) -> bool:
        return time() > self.timeout
