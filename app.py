import os
from flask import Flask, request, render_template, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
# Assume your API client code is saved in a module
from api_client import client

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
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error=True)
    return render_template('login.html', error=False)


@app.route('/media_library')
def media_library():
    if 'jwt' not in session:
        return redirect(url_for('login'))
    media_list = api_client.search_media_in_library()
    return render_template('media_library.html', media_list=media_list)


def filter_format_tags(client):
    tag_types = client.get_available_tag_types()
    format_type_id = next(
        (type.id for type in tag_types if type.name == 'format'), None)
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
        tags = list(request.form.get('format_tag'))
        tags = [api_client.get_tag_by_id(tag_id).to_dict() for tag_id in tags]
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
            return redirect(url_for('upload'))
    tags = filter_format_tags(api_client)
    print('Tags:', tags)
    return render_template('upload.html', tags=[tag.to_dict() for tag in tags])

def logout():
    session.pop('jwt', None)
    return redirect(url_for('login'))

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'mp3', 'wav', 'ogg'}



if __name__ == '__main__':
    app.run(debug=True)
