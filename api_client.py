import json
import mimetypes
import os
from time import time
import jwt
import music_tag
from pytz import timezone
import requests
from secret import USER_ID, LOGIN, PASSWORD
from data_types import Tag, Media, Segment, TagType
from datetime import datetime, timedelta
# Constants


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

    def __init__(self) -> None:
        self.cache_dir = '.cache'
        self.jwt = None
        self.auth_header = None
        self.user_info = self.__recover_user_info()
        self.library = None
        self.schedule = None
        self.time_horizon = None

    def __add_token(self, token: str) -> None:
        payload = jwt.decode(token, options={"verify_signature": False})
        timeout = payload['exp']
        self.jwt = JWT(token, timeout)

    def __refresh_jwt_if_needed(self) -> None:
        now = time()
        if now > self.jwt.timeout:
            self.login(self.user_info.values())

    def __recover_user_info(self) -> dict:
        try:
            r = open(self.cache_dir+'/users.json')
            return json.load(r)
        except FileNotFoundError:
            return {}
        except Exception as e:
            print("Exception when calling __recover_user_info: %s\n" % e)
            raise e

    def __save_user(self, login: str, password: str) -> None:
        self.user_info = {
            'login': login,
            'pass': password
        }
        with open(self.cache_dir+'/users.json', 'w') as wr:
            json.dump(self.user_info, wr)

    def login(self, login: str, password: str) -> bool:
        url = f'{self.base_url}/admin/login'
        data = {'login': login, 'pass': password}

        try:
            api_response = requests.post(url, json=data)
            self.__add_token(api_response.json()['token'])
            self.auth_header = {'Authorization': f'Bearer {self.jwt.token}'}
            self.__save_user(login, password)
            return True
        except Exception as e:
            print("Exception when calling AuthApi->admin_login_post: %s\n" % e)
            if e.status == 400:
                return False
            return None

    # Media Handling

    def search_media_in_library(self, name: str = None, author: str = None, tags: list[Tag] = None, res_len: int = 5):
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/library/media'
        params = {'name': name, 'author': author,
                  'tags': tags, 'res_len': res_len}
        response = requests.get(url, headers=self.auth_header, params=params)
        if response.status_code != 200:
            raise ValueError(response.status_code, response.json())
        return response.json()['library']

    def get_media(self, media_id: int) -> Media:
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/library/media/{media_id}'
        response = requests.get(url, headers=self.auth_header)
        if response.status_code != 200:
            raise ValueError(response.status_code, response.json())
        media = Media.from_dict(response.json()['media'])
        return media

    def post_media_with_source(self, name: str, author: str, source: str, tags: list) -> int:
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/library/media'
        media = Media(name=name, author=author, tags=tags)
        try:
            is_valid_file(source)
        except FileNotFoundError as e:
            print(e)
            return
        except TypeError as e:
            print(e)
            return
        metadata = extract_metadata_and_remove_artwork(source)
        if metadata['name']:
            media.name = metadata['name']
        if metadata['author']:
            media.author = metadata['author']

        # https://requests.readthedocs.io/en/latest/user/advanced/#post-multiple-multipart-encoded-files
        files = [('source', (os.path.basename(source), open(source, 'rb'), 'audio/mpeg')),
                 ('media', (None, json.dumps(media.to_dict()), 'application/json'))]
        response = requests.post(
            url, headers=self.auth_header, files=files)
        if response.status_code != 200:
            if response.status_code >= 500:
                raise ValueError(response.status_code, 'server error')
            raise ValueError(response.status_code, response.json())
        return response.json()['id']

    def update_media_information(self,  media_id: int, name: str, author: str, tags: list[Tag]):
        self.__refresh_jwt_if_needed()
        media = Media(id=media_id, name=name, author=author, tags=tags)
        url = f'{self.base_url}/admin/library/media/{media_id}'
        response = requests.put(url, headers=self.auth_header, json={
                                'media': media.to_dict()})
        if response.status_code != 200:
            raise ValueError(response.status_code, response.json())
        return response

    def delete_media_by_id(self, media_id: int):
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/library/media/{media_id}'
        response = requests.delete(url, headers=self.auth_header)
        if response.status_code != 200:
            raise ValueError(response.status_code, response.json())
        return response

    # Tag Handling

    def get_available_tag_types(self) -> list[TagType]:
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/library/tag/types'
        response = requests.get(url, headers=self.auth_header)
        if response.status_code != 200:
            raise ValueError(response.status_code, response.json())
        return [TagType.from_dict(item) for item in response.json()['types']]

    def get_all_registered_tags(self) -> list[Tag]:
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/library/tag'
        response = requests.get(url, headers=self.auth_header)
        if response.status_code != 200:
            raise ValueError(response.status_code, response.json())
        return [Tag.from_dict(item) for item in response.json()['tags']]

    def register_new_tag(self, tag_name: str, tag_type: dict, meta: dict = {}):
        self.__refresh_jwt_if_needed()
        tag_type = TagType(id=tag_type['id'], name=tag_type['name'])
        tag = Tag(name=tag_name, type=tag_type, meta=meta)
        url = f'{self.base_url}/admin/library/tag'
        response = requests.post(url, headers=self.auth_header, json={
                                 'tag': tag.to_dict()})
        if response.status_code != 200:
            raise ValueError(response.status_code, response.json())
        response = response.json()['id']
        return response

    def update_tag(self, tag_id: int, tag_name: str, tag_type: dict, meta: dict = {}):
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/library/tag'
        tag_type = TagType(id=tag_type['id'], name=tag_type['name'])
        tag = Tag(id=tag_id, name=tag_name, type=tag_type, meta=meta)
        response = requests.put(url, headers=self.auth_header, json={
                                'tag': tag.to_dict()})
        return response

    def get_tag_by_id(self, tag_id: int) -> Tag:
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/library/tag/{tag_id}'
        response = requests.get(url, headers=self.auth_header)
        if response.status_code != 200:
            raise ValueError(response.status_code, response.json())
        tag = Tag.from_dict(response.json()['tag'])
        return tag

    def delete_tag_by_id(self, tag_id: int):
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/library/tag/{tag_id}'
        response = requests.delete(url, headers=self.auth_header)
        if response.status_code != 200:
            raise ValueError(response.status_code, response.json())
        return response

    # Schedule and Segment Management

    def get_schedule(self, start=None, stop=None):
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/schedule'
        params = {}
        if start is not None:
            params['start'] = start
        if stop is not None:
            params['stop'] = stop
        response = requests.get(url, headers=self.auth_header, params=params)
        if response.status_code != 200:
            raise ValueError(response.status_code, response.json())
        self.schedule = response.json()['segments']
        if len(self.schedule) > 0:
            start = datetime.strptime(
                self.schedule[-1]['start'], r'%Y-%m-%dT%H:%M:%S.%f%z')
            duration = timedelta(
                microseconds=self.schedule[-1]['stopCut']*1e-3)
            self.time_horizon = start + duration
        return response

    def create_new_segment(self, media_id: int, time: datetime = None) -> int:
        self.__refresh_jwt_if_needed()
        self.get_schedule()

        now = datetime.now(tz=timezone('UTC'))
        if self.time_horizon is None or self.time_horizon < now:
            self.time_horizon = now

        media = self.get_media(media_id)
        if media is None:
            raise ValueError("Unknown media_id.")

        start = self.time_horizon
        if time is not None:
            start = time

        segment = Segment(
            media_id=media_id,
            start=start.strftime(r"%Y-%m-%dT%H:%M:%S.%f+00:00"),
            begin_cut=0,
            stop_cut=media.duration
        )
        url = f'{self.base_url}/admin/schedule'
        body = {'segment': segment.to_dict()}
        response = requests.post(url, headers=self.auth_header, json=body)
        if response.status_code == 200:
            self.time_horizon = start + \
                timedelta(microseconds=media.duration*1e3)
            response = response.json()['id']
            return response
        elif response.status_code == 400:
            if response.json()['error'] == 'segment intersection':
                print('Segment intersection')
            else:
                raise ValueError(response.json())

    def clear_schedule_from_timestamp(self, timestamp: datetime):
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/schedule'
        params = {'from': timestamp}
        response = requests.delete(
            url, headers=self.auth_header, params=params)
        if response.status_code != 200:
            raise ValueError(response.status_code, response.json())
        return response

    def get_segment_by_id(self, segment_id: int) -> Segment:
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/schedule/{segment_id}'
        response = requests.get(url, headers=self.auth_header)
        if response.status_code != 200:
            raise ValueError(response.status_code, response.json())
        segment = Segment.from_dict(response.json()['segment'])
        return segment

    def delete_segment_by_id(self, segment_id: int):
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/schedule/{segment_id}'
        response = requests.delete(url, headers=self.auth_header)
        if response.status_code != 200:
            raise ValueError(response.status_code, response.json())
        return response

    # Radio Control

    def start_radio(self):
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/radio/start'
        response = requests.get(url, headers=self.auth_header)
        if response.status_code != 200:
            raise ValueError(response.status_code, response.json())
        return response

    def stop_radio(self):
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/radio/stop'
        response = requests.get(url, headers=self.auth_header)
        if response.status_code != 200:
            raise ValueError(response.status_code, response.json())
        return response


class JWT:
    def __init__(self, token, timeout) -> None:
        self.token = token
        self.timeout = timeout


# Authentication


# def admin_login(login, password):
#     url = f'{self.base_url}/admin/login'
#     data = {'login': login, 'pass': password}
#     response = requests.post(url, json=data)
#     return response
# Example Usage
if __name__ == '__main__':

    cl = client()
    cl.login('fedorthewise', 'pyxSR73ZdCFX')
    print(cl.get_available_tag_types())
    song_tag = {'id': 1, 'name': 'song', 'type': {
        'id': 1, 'name': 'format'}, 'meta': None}
    print(cl.post_media_with_source('Sky', 'NAVIBAND',
          '../tmp/downloaded/NAVIBAND - Мары.mp3', [song_tag]))
    print(cl.search_media_in_library(name='O, Moda Moda').json())
