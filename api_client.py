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
            self.login(*(self.user_info.values()[0]))

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

    def fetch_all_media(self) -> list[Media]:
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/library/media'
        response = requests.get(url, headers=self.auth_header)
        if response.status_code != 200:
            raise ValueError(response.status_code, response.json())
        self.library = {int(item['id']): Media.from_dict(item) for item in response.json()['library']}

    def search_media_in_library(self, name: str = None, author: str = None, tags: list[Tag] = None, res_len: int = 5):
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/admin/library/media'
        if tags is not None:
            tags = [Tag(id=tag['id'], name=tag['name'], type=TagType(id=tag['type']['id'], name=tag['type']['name']), meta=tag['meta']) for tag in tags]
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
        else:
            params['start'] = datetime.now().strftime('%s')
        if stop is not None:
            params['stop'] = stop
        response = requests.get(url, headers=self.auth_header, params=params)
        if response.status_code != 200:
            raise ValueError(response.status_code, response.json())
        self.schedule = response.json()['segments']
        if len(self.schedule) > 0:
            try:
                start = datetime.strptime(
                    self.schedule[-1]['start'], r'%Y-%m-%dT%H:%M:%S.%f%z')
            except Exception as e:
                print(e)
                start = datetime.strptime(
                    self.schedule[-1]['start'], r'%Y-%m-%dT%H:%M:%S%z')
            duration = timedelta(
                microseconds=self.schedule[-1]['stopCut']*1e-3)
            self.time_horizon = start + duration
            self.fetch_all_media()
            now = datetime.now(tz=timezone('UTC'))
            for item in self.schedule:
                duration = timedelta(
                    microseconds=item['stopCut']*1e-3)
                try:
                    item['end'] = datetime.strftime(datetime.strptime(
                        item['start'], r'%Y-%m-%dT%H:%M:%S.%f%z') + duration, r'%Y-%m-%dT%H:%M:%S.%f%z')
                    # print(item['end'])
                except Exception as e:
                    print(e)
                    item['end'] = datetime.strftime(datetime.strptime(
                        item['start'], r'%Y-%m-%dT%H:%M:%S%z') + duration, r'%Y-%m-%dT%H:%M:%S.%f%z')
            self.schedule = [item for item in self.schedule if datetime.strptime(
                item['end'], r'%Y-%m-%dT%H:%M:%S.%f%z') > now]
            for item in self.schedule:
                item['mediaTitle'] = self.library[int(
                    item['mediaID'])].author + ' - ' + self.library[int(item['mediaID'])].name
        return self.schedule

    def create_new_segment(self, media_id: int, *, time: datetime = None, stop_cut: int = None) -> int:
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

        if stop_cut is None:
            stop_cut = media.duration

        segment = Segment(
            mediaID=media_id,
            start=start.strftime(r"%Y-%m-%dT%H:%M:%S.%f+00:00"),
            beginCut=0,
            stopCut=stop_cut
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
            try:
                if response.json()['error'] == 'segment intersection':
                    return -1
                else:
                    raise ValueError(response.json())
            except Exception as e:
                raise ValueError(response.text, response.request.body)

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
        segment_dict = response.json()['segment']
        segment_dict.pop('protected', None)
        segment = Segment.from_dict(segment_dict)
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
    
    # Live control

    def start_live(self):
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/live/start'
        response = requests.get(url, headers=self.auth_header)
        if response.status_code != 200:
            raise ValueError(response.status_code, response.json())
        return response
    
    def stop_live(self):
        self.__refresh_jwt_if_needed()
        url = f'{self.base_url}/live/stop'
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
