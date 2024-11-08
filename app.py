from flask import Flask, jsonify, request, render_template, redirect, url_for, session, flash, g
from werkzeug.utils import secure_filename
import os
import logging
from datetime import datetime, timedelta
from urllib.parse import urlparse, urljoin

# Import the API client and custom exceptions
from api_client import client as APIClient, AuthenticationError, AuthorizationError, NotFoundError, ValidationError, ServerError, APIClientError

# Initialize Flask app
app = Flask(__name__)

# Configure secret key and upload folder from environment variables for security
# Replace with a secure key in production
app.secret_key = os.getenv('SECRET_KEY', 'your_default_secret_key')

UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def is_safe_url(target):
    """
    Ensure that the URL is safe to redirect to by confirming it's a relative URL.
    Prevents Open Redirect vulnerabilities.
    """
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return (
        test_url.scheme in ('http', 'https') and
        ref_url.netloc == test_url.netloc
    )


@app.before_request
def before_request_func():
    """
    Initialize the API client before each request.
    If the user is not authenticated, redirect to the login page with a 'next' parameter.
    """
    if 'jwt' in session:
        token = session['jwt']
        g.api_client = APIClient(token=token)
    else:
        g.api_client = None
        # Allow access to login, static, and favicon routes without JWT
        if request.endpoint not in ('login', 'static', 'favicon'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))


@app.teardown_request
def teardown_request_func(exception):
    """
    Cleanup after each request.
    """
    api_client = getattr(g, 'api_client', None)
    if api_client:
        # Perform any necessary cleanup here
        pass


@app.route('/')
def index():
    """
    Redirect to login if not authenticated, else to media library.
    """
    if not g.api_client:
        return redirect(url_for('login'))
    return redirect(url_for('media_library'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    Handle user login.
    After successful login, redirect to the 'next' URL if it's safe, else to the media library.
    """
    if request.method == 'POST':
        login_data = request.form.get('login')
        password_data = request.form.get('password')
        # Retrieve 'next' parameter from query string
        next_url = request.args.get('next')

        # Input validation
        if not login_data or not password_data:
            flash('Please enter both login and password.', 'warning')
            return render_template('login.html', error=True, next=next_url)

        try:
            api_client = APIClient()
            if api_client.login(login_data, password_data):
                # Store JWT token in session
                session['jwt'] = api_client.jwt.token
                flash('Logged in successfully!', 'success')
                # Validate the 'next' URL to prevent open redirects
                if next_url and is_safe_url(next_url):
                    return redirect(next_url)
                else:
                    return redirect(url_for('media_library'))
            else:
                flash('Invalid login credentials.', 'danger')
                return render_template('login.html', error=True, next=next_url)
        except AuthenticationError as e:
            flash(str(e), 'danger')
            return render_template('login.html', error=True, next=next_url)
        except APIClientError as e:
            flash('An unexpected error occurred. Please try again.', 'danger')
            logger.error(f"APIClientError during login: {e}")
            return render_template('login.html', error=True, next=next_url)

    # GET request
    next_url = request.args.get('next')  # Capture 'next' parameter if present
    return render_template('login.html', error=False, next=next_url)


@app.route('/logout')
def logout():
    """
    Handle user logout.
    """
    session.pop('jwt', None)
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))


@app.route('/media_library', methods=['GET', 'POST'])
def media_library():
    """
    Display the media library.
    """
    if not g.api_client:
        flash('Please log in to access the media library.', 'warning')
        return redirect(url_for('login', next=request.url))

    try:
        media_list = g.api_client.search_media_in_library()
        # Convert custom Media objects to dictionaries
        media_list_dict = [media.to_dict() for media in media_list]
        return render_template('media_library.html', media_list=media_list_dict)
    except AuthenticationError:
        flash('Session expired. Please log in again.', 'warning')
        return redirect(url_for('login', next=request.url))
    except NotFoundError:
        flash('Media library not found.', 'warning')
        return render_template('media_library.html', media_list=[])
    except ServerError:
        flash('Server error occurred while fetching media.', 'danger')
        return render_template('media_library.html', media_list=[])
    except APIClientError as e:
        flash('An unexpected error occurred while fetching media.', 'danger')
        logger.error(f"APIClientError in media_library: {e}")
        return render_template('media_library.html', media_list=[])


@app.route('/media/<int:media_id>', methods=['POST', 'DELETE'])
def delete_media_from_library_by_id(media_id):
    """
    Delete a media item by its ID.
    """
    if not g.api_client:
        flash('Please log in to perform this action.', 'warning')
        return redirect(url_for('login', next=request.url))

    if request.method == 'DELETE':
        try:
            g.api_client.delete_media_by_id(media_id)
            flash('Media deleted successfully.', 'success')
            return '', 204
        except NotFoundError:
            flash(f'Media with ID {media_id} not found.', 'warning')
            return jsonify({'error': 'Media not found'}), 404
        except AuthorizationError:
            flash('You do not have permission to delete this media.', 'danger')
            return jsonify({'error': 'Forbidden'}), 403
        except ServerError:
            flash('Server error occurred while deleting media.', 'danger')
            return jsonify({'error': 'Server error'}), 500
        except APIClientError as e:
            flash('An unexpected error occurred while deleting media.', 'danger')
            logger.error(
                f"APIClientError in delete_media_from_library_by_id: {e}")
            return jsonify({'error': 'Internal server error'}), 500
    else:
        flash('Invalid request method.', 'danger')
        return jsonify({'error': 'Invalid method'}), 405


def filter_format_tags(api_client):
    """
    Retrieve and filter tags of type 'format'.
    """
    try:
        tag_types = api_client.get_available_tag_types()
        format_type = next(
            (tt for tt in tag_types if tt.name.lower() == 'format'), None)
        if not format_type:
            flash('Format tag type not found.', 'warning')
            return []

        all_tags = api_client.get_all_registered_tags()
        format_tags = [
            tag for tag in all_tags if tag.type.id == format_type.id]
        return format_tags
    except APIClientError as e:
        flash('Failed to retrieve format tags.', 'danger')
        logger.error(f"APIClientError in filter_format_tags: {e}")
        return []


def filter_podcast_tags(api_client):
    """
    Retrieve and filter tags of type 'podcast'.
    """
    try:
        tag_types = api_client.get_available_tag_types()
        podcast_type = next(
            (tt for tt in tag_types if tt.name.lower() == 'podcast'), None)
        if not podcast_type:
            flash('Podcast tag type not found.', 'warning')
            return []

        all_tags = api_client.get_all_registered_tags()
        podcast_tags = [
            tag for tag in all_tags if tag.type.id == podcast_type.id]
        return podcast_tags
    except APIClientError as e:
        flash('Failed to retrieve podcast tags.', 'danger')
        logger.error(f"APIClientError in filter_podcast_tags: {e}")
        return []


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    """
    Handle media upload.
    """
    if not g.api_client:
        flash('Please log in to upload media.', 'warning')
        return redirect(url_for('login', next=request.url))

    if request.method == 'POST':
        name = request.form.get('name')
        author = request.form.get('author')
        tag_ids = request.form.getlist(
            'format_tag') + request.form.getlist('podcast_tag')
        file = request.files.get('source')

        # Input validation
        if not name or not author or not tag_ids or not file:
            flash('All fields are required.', 'warning')
            return redirect(url_for('upload'))

        try:
            # Convert tag IDs to integers
            tag_ids = list(map(int, tag_ids))
            # Retrieve Tag objects
            tags = [g.api_client.get_tag_by_id(
                tag_id).to_dict() for tag_id in tag_ids]
        except ValueError:
            flash('Invalid tag IDs provided.', 'danger')
            return redirect(url_for('upload'))
        except NotFoundError:
            flash('One or more tags not found.', 'warning')
            return redirect(url_for('upload'))
        except APIClientError as e:
            flash('Failed to retrieve tags.', 'danger')
            logger.error(f"APIClientError in upload (tag retrieval): {e}")
            return redirect(url_for('upload'))

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            try:
                file.save(file_path)
                logger.info(
                    f"Uploading media: {name} by {author} with tags {tags} from {file_path}")
                media_id = g.api_client.post_media_with_source(
                    name, author, file_path, tags)
                flash(
                    f'Media uploaded successfully! ID: {media_id}', 'success')
            except ValidationError as e:
                flash(f'Validation Error: {e}', 'danger')
            except ServerError:
                flash('Server error occurred while uploading media.', 'danger')
            except APIClientError as e:
                flash('An unexpected error occurred while uploading media.', 'danger')
                logger.error(f"APIClientError in upload (media upload): {e}")
            finally:
                # Remove the file after attempting upload
                if os.path.exists(file_path):
                    os.remove(file_path)
            return redirect(url_for('upload'))
        else:
            flash('Invalid file type. Allowed types: mp3, wav, ogg.', 'warning')
            return redirect(url_for('upload'))

    try:
        tags = filter_format_tags(g.api_client)
        podcast_tags = filter_podcast_tags(g.api_client)
        tags_dict = [tag.to_dict() for tag in tags]
        podcast_tags_dict = [tag.to_dict() for tag in podcast_tags]
        return render_template('upload.html', tags=tags_dict, podcast_tags=podcast_tags_dict)
    except AuthenticationError:
        flash('Session expired. Please log in again.', 'warning')
        return redirect(url_for('login', next=request.url))
    except NotFoundError:
        flash('Tag types not found.', 'warning')
        return render_template('upload.html', tags=[], podcast_tags=[])
    except ServerError:
        flash('Server error occurred while loading tags.', 'danger')
        return render_template('upload.html', tags=[], podcast_tags=[])
    except APIClientError as e:
        flash('An unexpected error occurred while loading tags.', 'danger')
        logger.error(f"APIClientError in upload (tag loading): {e}")
        return render_template('upload.html', tags=[], podcast_tags=[])


@app.route('/schedule')
def view_schedule():
    """
    Display the schedule.
    """
    if not g.api_client:
        flash('Please log in to view the schedule.', 'warning')
        return redirect(url_for('login', next=request.url))

    try:
        schedule = g.api_client.get_schedule()
        schedule_dict = [segment.to_dict() for segment in schedule]
        tags = filter_format_tags(g.api_client)
        tags_dict = [tag.to_dict() for tag in tags]
        return render_template('schedule.html', schedule=schedule_dict, format_tags=tags_dict)
    except AuthenticationError:
        flash('Session expired. Please log in again.', 'warning')
        return redirect(url_for('login', next=request.url))
    except NotFoundError:
        flash('Schedule not found.', 'warning')
        return redirect(url_for('media_library'))
    except ServerError:
        flash('Server error occurred while fetching schedule.', 'danger')
        return redirect(url_for('media_library'))
    except APIClientError as e:
        flash('An unexpected error occurred while fetching schedule.', 'danger')
        logger.error(f"APIClientError in view_schedule: {e}")
        return redirect(url_for('media_library'))


@app.route('/api/schedule', methods=['GET'])
def raw_schedule():
    """
    Return the schedule as JSON.
    """
    if not g.api_client:
        flash('Please log in to access this API.', 'warning')
        return redirect(url_for('login', next=request.url))

    try:
        schedule = g.api_client.get_schedule()
        schedule_dict = [segment.to_dict() for segment in schedule]
        return jsonify(schedule_dict)
    except AuthenticationError:
        flash('Session expired. Please log in again.', 'warning')
        return redirect(url_for('login', next=request.url))
    except NotFoundError:
        return jsonify({'error': 'Schedule not found.'}), 404
    except ServerError:
        return jsonify({'error': 'Server error occurred while fetching schedule.'}), 500
    except APIClientError as e:
        flash('An unexpected error occurred.', 'danger')
        logger.error(f"APIClientError in raw_schedule: {e}")
        return jsonify({'error': 'Internal server error.'}), 500


@app.route('/api/search_media', methods=['GET'])
def api_search_media():
    """
    Search media in the library based on query parameters.
    """
    if not g.api_client:
        flash('Please log in to access this API.', 'warning')
        return redirect(url_for('login', next=request.url))

    name = request.args.get('name')
    author = request.args.get('author')
    tags = request.args.getlist('tags')
    res_len = request.args.get('res_len', 5)

    try:
        # Convert tag IDs to integers
        tags = list(map(int, tags)) if tags else []
        # Retrieve Tag objects
        tags_data = [g.api_client.get_tag_by_id(
            tag_id).to_dict() for tag_id in tags]
    except ValueError:
        flash('Invalid tag IDs provided.', 'danger')
        return jsonify({'error': 'Invalid tag IDs.'}), 400
    except NotFoundError:
        flash('One or more tags not found.', 'warning')
        return jsonify({'error': 'Tags not found.'}), 404
    except APIClientError as e:
        flash('Failed to retrieve tags.', 'danger')
        logger.error(
            f"APIClientError in api_search_media (tag retrieval): {e}")
        return jsonify({'error': 'Internal server error.'}), 500

    try:
        media_list = g.api_client.search_media_in_library(
            name=name, author=author, tags=tags_data, res_len=int(res_len))
        media_list_dict = [media.to_dict() for media in media_list]
        return jsonify(media_list_dict)
    except ValidationError as e:
        flash(f'Validation Error: {e}', 'danger')
        return jsonify({'error': 'Validation error.'}), 400
    except NotFoundError:
        flash('No media found matching the criteria.', 'warning')
        return jsonify({'error': 'No media found.'}), 404
    except ServerError:
        flash('Server error occurred while searching media.', 'danger')
        return jsonify({'error': 'Server error.'}), 500
    except APIClientError as e:
        flash('An unexpected error occurred while searching media.', 'danger')
        logger.error(f"APIClientError in api_search_media: {e}")
        return jsonify({'error': 'Internal server error.'}), 500


@app.route('/api/schedule_track', methods=['POST'])
def api_schedule_track():
    """
    Schedule a new track.
    """
    if not g.api_client:
        flash('Please log in to access this API.', 'warning')
        return redirect(url_for('login', next=request.url))

    data = request.get_json()

    if not data:
        flash('No data provided.', 'warning')
        return jsonify({'error': 'No data provided.'}), 400

    media_id = data.get('media_id')
    start_time_str = data.get('start_time')
    duration = data.get('duration')

    if not media_id or not start_time_str:
        flash('Media ID and start time are required.', 'warning')
        return jsonify({'error': 'Media ID and start time are required.'}), 400

    try:
        # Attempt to parse the start time
        try:
            start_time = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            start_time = datetime.strptime(
                start_time_str, '%Y-%m-%dT%H:%M:%S.%f%z')
    except ValueError:
        flash('Invalid start time format.', 'danger')
        return jsonify({'error': 'Invalid start time format.'}), 400

    try:
        result = g.api_client.create_new_segment(
            media_id=media_id, time=start_time, stop_cut=duration)
        if result == -1:
            flash('Failed to schedule track due to segment intersection.', 'danger')
            return jsonify({'error': 'Segment intersection detected.'}), 400
        flash('Track scheduled successfully.', 'success')
        return jsonify({'id': result}), 201
    except ValidationError as e:
        flash(f'Validation Error: {e}', 'danger')
        return jsonify({'error': 'Validation error.'}), 400
    except NotFoundError:
        flash('Media not found.', 'warning')
        return jsonify({'error': 'Media not found.'}), 404
    except ServerError:
        flash('Server error occurred while scheduling track.', 'danger')
        return jsonify({'error': 'Server error.'}), 500
    except APIClientError as e:
        flash('An unexpected error occurred while scheduling track.', 'danger')
        logger.error(f"APIClientError in api_schedule_track: {e}")
        return jsonify({'error': 'Internal server error.'}), 500


@app.route('/delete_segment/<int:segment_id>', methods=['POST', 'DELETE'])
def delete_segment(segment_id):
    """
    Delete a segment by its ID.
    """
    if not g.api_client:
        flash('Please log in to perform this action.', 'warning')
        return redirect(url_for('login', next=request.url))

    if request.method == 'DELETE':
        try:
            g.api_client.delete_segment_by_id(segment_id)
            flash('Segment deleted successfully.', 'success')
            return '', 204
        except NotFoundError:
            flash(f'Segment with ID {segment_id} not found.', 'warning')
            return jsonify({'error': 'Segment not found.'}), 404
        except AuthorizationError:
            flash('You do not have permission to delete this segment.', 'danger')
            return jsonify({'error': 'Forbidden.'}), 403
        except ServerError:
            flash('Server error occurred while deleting segment.', 'danger')
            return jsonify({'error': 'Server error.'}), 500
        except APIClientError as e:
            flash('An unexpected error occurred while deleting segment.', 'danger')
            logger.error(f"APIClientError in delete_segment: {e}")
            return jsonify({'error': 'Internal server error.'}), 500
    else:
        flash('Invalid request method.', 'danger')
        return jsonify({'error': 'Invalid method.'}), 405


@app.route('/api/move_segment', methods=['POST'])
def move_segment():
    """
    Move a segment relative to another segment.
    """
    if not g.api_client:
        flash('Please log in to access this API.', 'warning')
        return redirect(url_for('login', next=request.url))

    data = request.get_json()

    if not data:
        flash('No data provided.', 'warning')
        return jsonify({'error': 'No data provided.'}), 400

    current_segment_id = data.get('currentSegmentId')
    adjacent_segment_id = data.get('adjacentSegmentId')
    direction = data.get('direction')
    top_start_time = data.get('topStartTime')
    top_end_time = data.get('topEndTime')

    if not direction:
        flash('Direction is required.', 'warning')
        return jsonify({'error': 'Direction is required.'}), 400

    try:
        # Retrieve segments if IDs are provided
        current_segment = g.api_client.get_segment_by_id(
            current_segment_id) if current_segment_id else None
        adjacent_segment = g.api_client.get_segment_by_id(
            adjacent_segment_id) if adjacent_segment_id else None
    except NotFoundError:
        flash('One or more segments not found.', 'warning')
        return jsonify({'error': 'Segments not found.'}), 404
    except APIClientError as e:
        flash('Failed to retrieve segments.', 'danger')
        logger.error(
            f"APIClientError in move_segment (segment retrieval): {e}")
        return jsonify({'error': 'Internal server error.'}), 500

    try:
        if current_segment:
            if not adjacent_segment:
                if direction == 'down':
                    current_segment_new_start = datetime.strptime(
                        top_end_time, '%Y-%m-%dT%H:%M:%S.%f%z') - timedelta(milliseconds=current_segment.stop_cut)
                    g.api_client.delete_segment_by_id(current_segment_id)
                    g.api_client.create_new_segment(
                        media_id=current_segment.media_id,
                        time=current_segment_new_start,
                        stop_cut=current_segment.stop_cut
                    )
                elif direction == 'up':
                    current_segment_new_start = datetime.strptime(
                        top_start_time, '%Y-%m-%dT%H:%M:%S.%f%z')
                    g.api_client.delete_segment_by_id(current_segment_id)
                    g.api_client.create_new_segment(
                        media_id=current_segment.media_id,
                        time=current_segment_new_start,
                        stop_cut=current_segment.stop_cut
                    )
                else:
                    flash('Invalid direction provided.', 'danger')
                    return jsonify({'status': 'error', 'message': 'Direction is invalid'}), 400
            else:
                if direction == 'down':
                    current_segment_new_start = datetime.strptime(
                        current_segment.start, '%Y-%m-%dT%H:%M:%S.%f%z') + timedelta(milliseconds=adjacent_segment.stop_cut)

                    # Delete both segments
                    g.api_client.delete_segment_by_id(current_segment_id)
                    g.api_client.delete_segment_by_id(adjacent_segment_id)

                    # Create new segments
                    g.api_client.create_new_segment(
                        media_id=current_segment.media_id,
                        time=current_segment_new_start,
                        stop_cut=current_segment.stop_cut
                    )
                    g.api_client.create_new_segment(
                        media_id=adjacent_segment.media_id,
                        time=datetime.strptime(
                            current_segment.start, '%Y-%m-%dT%H:%M:%S.%f%z'),
                        stop_cut=adjacent_segment.stop_cut
                    )
                elif direction == 'up':
                    adjacent_segment_new_start = datetime.strptime(
                        adjacent_segment.start, '%Y-%m-%dT%H:%M:%S.%f%z') + timedelta(milliseconds=current_segment.stop_cut)

                    # Delete both segments
                    g.api_client.delete_segment_by_id(current_segment_id)
                    g.api_client.delete_segment_by_id(adjacent_segment_id)

                    # Create new segments
                    g.api_client.create_new_segment(
                        media_id=current_segment.media_id,
                        time=datetime.strptime(
                            adjacent_segment.start, '%Y-%m-%dT%H:%M:%S.%f%z'),
                        stop_cut=current_segment.stop_cut
                    )
                    g.api_client.create_new_segment(
                        media_id=adjacent_segment.media_id,
                        time=adjacent_segment_new_start,
                        stop_cut=adjacent_segment.stop_cut
                    )
                else:
                    flash('Invalid direction provided.', 'danger')
                    return jsonify({'status': 'error', 'message': 'Direction is invalid'}), 400
            flash('Segment moved successfully.', 'success')
            return jsonify({'status': 'success'}), 200
        else:
            flash('Segment not found.', 'warning')
            return jsonify({'status': 'error', 'message': 'Segment not found'}), 404
    except ValidationError as e:
        flash(f'Validation Error: {e}', 'danger')
        return jsonify({'status': 'error', 'message': 'Validation error'}), 400
    except ServerError:
        flash('Server error occurred while moving segment.', 'danger')
        return jsonify({'status': 'error', 'message': 'Server error'}), 500
    except APIClientError as e:
        flash('An unexpected error occurred while moving segment.', 'danger')
        logger.error(f"APIClientError in move_segment: {e}")
        return jsonify({'status': 'error', 'message': 'Internal server error'}), 500


@app.route('/live', methods=['GET'])
def live():
    """
    Display live sessions.
    """
    if not g.api_client:
        flash('Please log in to access live sessions.', 'warning')
        return redirect(url_for('login', next=request.url))

    try:
        # lives = g.api_client.get_lives()
        # lives_dict = [live.to_dict() for live in lives]
        return render_template('live.html', lives=[])
    except AuthenticationError:
        flash('Session expired. Please log in again.', 'warning')
        return redirect(url_for('login', next=request.url))
    except NotFoundError:
        flash('No live sessions found.', 'warning')
        return render_template('live.html', lives=[])
    except ServerError:
        flash('Server error occurred while fetching live sessions.', 'danger')
        return render_template('live.html', lives=[])
    except APIClientError as e:
        flash('An unexpected error occurred while fetching live sessions.', 'danger')
        logger.error(f"APIClientError in live: {e}")
        return render_template('live.html', lives=[])


@app.route('/api/get_live_status', methods=['GET'])
def get_live_status():
    """
    Get the current live status.
    """
    if not g.api_client:
        flash('Please log in to access this API.', 'warning')
        return redirect(url_for('login', next=request.url))

    try:
        live_status = g.api_client.get_live_status()
        return jsonify({'status': live_status})
    except NotFoundError:
        flash('Live status not found.', 'warning')
        return jsonify({'error': 'Live status not found.'}), 404
    except ServerError:
        flash('Server error occurred while fetching live status.', 'danger')
        return jsonify({'error': 'Server error.'}), 500
    except APIClientError as e:
        flash('An unexpected error occurred while fetching live status.', 'danger')
        logger.error(f"APIClientError in get_live_status: {e}")
        return jsonify({'error': 'Internal server error.'}), 500


@app.route('/api/start_live', methods=['POST'])
def start_live():
    """
    Start a live session.
    """
    if not g.api_client:
        flash('Please log in to access this API.', 'warning')
        return redirect(url_for('login', next=request.url))

    data = request.get_json()

    if not data or 'name' not in data:
        flash('Live session name is required.', 'warning')
        return jsonify({'error': 'Live session name is required.'}), 400

    name = data['name']

    try:
        g.api_client.start_live(name=name)
        flash('Live session started successfully.', 'success')
        return jsonify({'status': 'success'}), 200
    except ValidationError as e:
        flash(f'Validation Error: {e}', 'danger')
        return jsonify({'error': 'Validation error.'}), 400
    except AuthorizationError:
        flash('You do not have permission to start a live session.', 'danger')
        return jsonify({'error': 'Forbidden.'}), 403
    except ServerError:
        flash('Server error occurred while starting live session.', 'danger')
        return jsonify({'error': 'Server error.'}), 500
    except APIClientError as e:
        flash('An unexpected error occurred while starting live session.', 'danger')
        logger.error(f"APIClientError in start_live: {e}")
        return jsonify({'error': 'Internal server error.'}), 500


@app.route('/api/stop_live', methods=['POST'])
def stop_live():
    """
    Stop the current live session.
    """
    if not g.api_client:
        flash('Please log in to access this API.', 'warning')
        return redirect(url_for('login', next=request.url))

    try:
        g.api_client.stop_live()
        flash('Live session stopped successfully.', 'success')
        return jsonify({'status': 'success'}), 200
    except AuthorizationError:
        flash('You do not have permission to stop live session.', 'danger')
        return jsonify({'error': 'Forbidden.'}), 403
    except ServerError:
        flash('Server error occurred while stopping live session.', 'danger')
        return jsonify({'error': 'Server error.'}), 500
    except APIClientError as e:
        flash('An unexpected error occurred while stopping live session.', 'danger')
        logger.error(f"APIClientError in stop_live: {e}")
        return jsonify({'error': 'Internal server error.'}), 500


@app.route('/api/get_tag_types', methods=['GET'])
def get_tag_types():
    """
    Retrieve available tag types.
    """
    if not g.api_client:
        flash('Please log in to access this API.', 'warning')
        return redirect(url_for('login', next=request.url))

    try:
        tag_types = g.api_client.get_available_tag_types()
        tag_types_dict = [tag_type.to_dict() for tag_type in tag_types]
        return jsonify(tag_types_dict)
    except NotFoundError:
        flash('Tag types not found.', 'warning')
        return jsonify({'error': 'Tag types not found.'}), 404
    except ServerError:
        flash('Server error occurred while fetching tag types.', 'danger')
        return jsonify({'error': 'Server error.'}), 500
    except APIClientError as e:
        flash('An unexpected error occurred while fetching tag types.', 'danger')
        logger.error(f"APIClientError in get_tag_types: {e}")
        return jsonify({'error': 'Internal server error.'}), 500


@app.route('/api/get_tags', methods=['GET'])
def get_tags():
    """
    Retrieve all registered tags.
    """
    if not g.api_client:
        flash('Please log in to access this API.', 'warning')
        return redirect(url_for('login', next=request.url))

    try:
        tags = g.api_client.get_all_registered_tags()
        tags_dict = [tag.to_dict() for tag in tags]
        return jsonify(tags_dict)
    except NotFoundError:
        flash('Tags not found.', 'warning')
        return jsonify({'error': 'Tags not found.'}), 404
    except ServerError:
        flash('Server error occurred while fetching tags.', 'danger')
        return jsonify({'error': 'Server error.'}), 500
    except APIClientError as e:
        flash('An unexpected error occurred while fetching tags.', 'danger')
        logger.error(f"APIClientError in get_tags: {e}")
        return jsonify({'error': 'Internal server error.'}), 500


def allowed_file(filename):
    """
    Check if the uploaded file has an allowed extension.
    """
    allowed_extensions = {'mp3', 'wav', 'ogg'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


if __name__ == '__main__':
    app.run(debug=True, port=5001)
