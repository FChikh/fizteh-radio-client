from flask import request, jsonify
import os
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, render_template, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
# Assume your API client code is saved in a module
from api_client import client

# Create a Flask app
app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Necessary for session management

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Instantiate your API client
api_client = client()


@app.before_request
def before_request_func():
    if api_client.jwt is None:
        logout()

@app.route('/')
def index():
    if 'jwt' not in session:
        return redirect(url_for('login'))
    else:
        return redirect(url_for('media_library'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login = request.form['login']
        password = request.form['password']
        if api_client.login(login, password):
            session['jwt'] = api_client.jwt.token  # Store JWT token in session
            return redirect(url_for('media_library'))
        else:
            return render_template('login.html', error=True)
    return render_template('login.html', error=False)


@app.route('/media_library', methods=['GET', 'POST'])
def media_library():
    if 'jwt' not in session:
        return redirect(url_for('login'))
    media_list = api_client.search_media_in_library()
    return render_template('media_library.html', media_list=media_list)


@app.route('/media/<int:media_id>', methods=['POST', 'DELETE'])
def delete_media_from_library_by_id(media_id):
    if 'jwt' not in session:
        return redirect(url_for('login'))

    # Проверка, является ли запрос методом DELETE
    if request.method == 'DELETE':
        try:
            api_client.delete_media_by_id(media_id)
            return '', 204
        except Exception as e:
            return f"Failed to delete media item: {e}", 500

    
def filter_format_tags(client):
    tag_types = client.get_available_tag_types()
    format_type_id = next(
        (type.id for type in tag_types if type.name == 'format'), None)
    if format_type_id is None:
        raise Exception("Format type not found")

    all_tags = client.get_all_registered_tags()
    format_tags = [tag for tag in all_tags if tag.type.id == format_type_id]
    return format_tags


def filter_podcast_tags(client):
    tag_types = client.get_available_tag_types()
    format_type_id = next(
        (type.id for type in tag_types if type.name == 'podcast'), None)
    if format_type_id is None:
        raise Exception("Format type not found")

    all_tags = client.get_all_registered_tags()
    format_tags = [tag for tag in all_tags if tag.type.id == format_type_id]
    return format_tags


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'jwt' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name']
        author = request.form['author']
        # Assuming tags are submitted as a list of tag IDs
        tags = list(map(int, request.form.getlist('format_tag')))
        podcast_tags = list(map(int, request.form.getlist('podcast_tag')))
        tags = [api_client.get_tag_by_id(tag_id).to_dict() for tag_id in tags + podcast_tags]
        file = request.files['source']

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            print(name, author, tags, file_path)
            media_id = api_client.post_media_with_source(
                    name, author, file_path, tags)
            print(media_id)
            flash(f'Media uploaded successfully! ID: {media_id}', 'success')
            os.remove(file_path)
            return redirect(url_for('upload'))
    tags = filter_format_tags(api_client)
    podcast_tags = filter_podcast_tags(api_client)
    return render_template('upload.html', tags=[tag.to_dict() for tag in tags], podcast_tags=[tag.to_dict() for tag in podcast_tags])


@app.route('/schedule')
def view_schedule():
    if 'jwt' not in session:
        return redirect(url_for('login'))

    try:
        schedule = api_client.get_schedule()
        print(schedule)
        tags = filter_format_tags(api_client)
        return render_template('schedule.html', schedule=schedule, format_tags=[tag.to_dict() for tag in tags])
    except Exception as e:
        print(e, type(e))
        return redirect(url_for('media_library'))
    
@app.route('/api/schedule', methods=['GET'])
def raw_schedule():
    if 'jwt' not in session:
        return redirect(url_for('login'))

    try:
        schedule = api_client.get_schedule()
        return schedule
    except Exception as e:
        return {'error': f"Failed to load schedule: {e}"}


@app.route('/api/search_media', methods=['GET'])
def api_search_media():
    if 'jwt' not in session:
        return redirect(url_for('login'))
    name = request.args.get('name', None)
    author = request.args.get('author', None)
    if request.args.get('tags') is None or request.args.get('tags') == '':
        tags = []
    else:
        tags = request.args.getlist('tags')
    # Assuming tags are passed as query parameters
    tags = list(map(int, tags))
    tags = [api_client.get_tag_by_id(tag_id).to_dict()
            for tag_id in tags]
    print(tags)
    res_len = int(request.args.get('res_len', 5))
    media_list = api_client.search_media_in_library(
        name=name, author=author, tags=tags, res_len=res_len)
    return jsonify(media_list)


@app.route('/api/schedule_track', methods=['POST'])
def api_schedule_track():
    if 'jwt' not in session:
        return redirect(url_for('login'))
    data = request.json
    try:
        data['start_time'] = datetime.strptime(data['start_time'], r'%Y-%m-%d %H:%M:%S')
    except ValueError:
        data['start_time'] = datetime.strptime(
            data['start_time'], r'%Y-%m-%dT%H:%M:%S.%f%z')
    result = api_client.create_new_segment(
        media_id=data['media_id'], time=data['start_time'], stop_cut=data.get('duration', None))
    if result == -1:
        return jsonify({'error': 'Failed to schedule track; perhaps - track instersection'}), 500
    return jsonify(result), 201


@app.route('/delete_segment/<int:segment_id>', methods=['POST', 'DELETE'])
def delete_segment(segment_id):
    if 'jwt' not in session:
        return redirect(url_for('login'))

    try:
        api_client.delete_segment_by_id(segment_id)
        return '', 204
    except Exception as e:
        return f'Failed to delete schedule item: {e}', 500
    

@app.route('/api/move_segment', methods=['POST'])
def move_segment():
    data = request.json
    current_segment_id = data.get('currentSegmentId')
    adjacent_segment_id = data.get('adjacentSegmentId')
    direction = data.get('direction')
    top_start_time = data.get('topStartTime')
    top_end_time = data.get('topEndTime')

    current_segment, adjacent_segment = None, None

    # Получаем сегменты из базы данных
    if current_segment_id is not None:
        current_segment = api_client.get_segment_by_id(current_segment_id)
    if adjacent_segment_id is not None:
        adjacent_segment = api_client.get_segment_by_id(adjacent_segment_id)

    if current_segment is not None:
        if adjacent_segment is None:
            if direction == 'down':
                current_segment_new_start = datetime.strptime(
                    top_end_time, r'%Y-%m-%dT%H:%M:%S.%f%z') - timedelta(microseconds=current_segment.stop_cut // 1e3)
                api_client.delete_segment_by_id(current_segment_id)
                api_client.create_new_segment(
                    media_id=current_segment.media_id, time=current_segment_new_start, stop_cut=current_segment.stop_cut)
            elif direction == 'up':
                current_segment_new_start = datetime.strptime(top_start_time, r'%Y-%m-%dT%H:%M:%S.%f%z')
                api_client.delete_segment_by_id(current_segment_id)
                api_client.create_new_segment(
                    media_id=current_segment.media_id, time=current_segment_new_start, stop_cut=current_segment.stop_cut)
            else:
                return jsonify({'status': 'error', 'message': 'Direction is invalid'}), 404
            
            return jsonify({'status': 'success'}), 200

        else:
            if direction == 'down':
                current_segment_new_start = datetime.strptime(
                    current_segment.start, r'%Y-%m-%dT%H:%M:%S.%f%z') + timedelta(microseconds=adjacent_segment.stop_cut // 1e3)

                # Delete both initial segments
                api_client.delete_segment_by_id(current_segment_id)
                api_client.delete_segment_by_id(adjacent_segment_id)

                # Create new segments
                api_client.create_new_segment(
                    media_id=current_segment.media_id, time=current_segment_new_start, stop_cut=current_segment.stop_cut)
                api_client.create_new_segment(
                    media_id=adjacent_segment.media_id, time=datetime.strptime(
                        current_segment.start, r'%Y-%m-%dT%H:%M:%S.%f%z'), stop_cut=adjacent_segment.stop_cut)
            # Обмениваем времена начала и конца сегментов
                # current_segment.start, adjacent_segment.start = current_segment.start + adjacent_segment.stop_cut, current_segment.start
            elif direction == 'up':
                # current_segment.start, adjacent_segment.start = adjacent_segment.start, adjacent_segment.start + current_segment.stop_cut
                adjacent_segment_new_start = datetime.strptime(
                    adjacent_segment.start, r'%Y-%m-%dT%H:%M:%S.%f%z') + timedelta(microseconds=current_segment.stop_cut // 1e3)

                # Delete both initial segments
                api_client.delete_segment_by_id(current_segment_id)
                api_client.delete_segment_by_id(adjacent_segment_id)

                # Create new segments
                api_client.create_new_segment(
                    media_id=current_segment.media_id, time=datetime.strptime(
                        adjacent_segment.start, r'%Y-%m-%dT%H:%M:%S.%f%z'), stop_cut=current_segment.stop_cut)
                api_client.create_new_segment(
                    media_id=adjacent_segment.media_id, time=adjacent_segment_new_start, stop_cut=adjacent_segment.stop_cut)

            else:
                return jsonify({'status': 'error', 'message': 'Direction is invalid'}), 404
            # Сохранить изменения в базе данных
            return jsonify({'status': 'success'}), 200
    else:
        return jsonify({'status': 'error', 'message': 'Segment not found'}), 404
    
@app.route('/live', methods=['GET'])
def live():
    if 'jwt' not in session:
        return redirect(url_for('login'))

    # lives = api_client.get_lives()
    lives = []
    return render_template('live.html', lives=lives)

@app.route('/api/get_live_status', methods=['GET'])
def get_live_status():
    if 'jwt' not in session:
        return redirect(url_for('login'))

    live_status = api_client.get_live_status()
    return jsonify({'status': live_status})

@app.route('/api/start_live', methods=['POST'])
def start_live():
    if 'jwt' not in session:
        return redirect(url_for('login'))

    name = request.json['name']
    response = api_client.start_live(name=name)
    return jsonify({'status': 'success'}), 200

@app.route('/api/stop_live', methods=['POST'])
def stop_live():
    if 'jwt' not in session:
        return redirect(url_for('login'))

    response = api_client.stop_live()
    return jsonify({'status': 'success'}), 200

@app.route('/api/get_tag_types', methods=['GET'])
def get_tag_types():
    if 'jwt' not in session:
        return redirect(url_for('login'))

    tag_types = api_client.get_available_tag_types()
    return jsonify([tag_type.to_dict() for tag_type in tag_types])

@app.route('/api/get_tags', methods=['GET'])
def get_tags():
    if 'jwt' not in session:
        return redirect(url_for('login'))

    tags = api_client.get_all_registered_tags()
    return jsonify([tag.to_dict() for tag in tags])

@app.route('/logout')
def logout():
    session.pop('jwt', None)
    return redirect(url_for('login'))

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'mp3', 'wav', 'ogg'}



if __name__ == '__main__':
    app.run(debug=True, port=5001)
