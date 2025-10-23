import subprocess
import os
import shlex  # For safe command argument building
from flask import Flask, render_template, jsonify, request, send_file, abort
from werkzeug.utils import secure_filename

# --- CONFIGURATION ---
# !! THIS IS THE ONLY PLACE YOU NEED TO CHANGE THE PASSWORD !!
DB_PASSWORD = "e#dE92e935"
# ---------------------

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = '/tmp'

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- Helper Function ---
def run_command(command, get_output=False):
    """Runs shell commands safely."""
    try:
        if get_output:
            result = subprocess.run(
                command, shell=True, check=True, capture_output=True, text=True, cwd=PROJECT_DIR
            )
            return {"success": True, "output": result.stdout, "error": result.stderr}
        else:
            subprocess.run(command, shell=True, check=True, cwd=PROJECT_DIR)
            return {"success": True, "output": "Command executed successfully."}
    except subprocess.CalledProcessError as e:
        return {"success": False, "output": e.stdout, "error": e.stderr}
    except Exception as e:
        return {"success": False, "error": str(e)}

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/deploy', methods=['POST'])
def deploy():
    run_command("docker compose pull")
    result = run_command("docker compose up -d")
    return jsonify(result)

@app.route('/backup', methods=['POST'])
def backup():
    backup_file = "/tmp/mongo_backup.gz"
    try:
        with open(os.path.join(PROJECT_DIR, 'docker-compose.yml'), 'r') as f:
            if DB_PASSWORD == "YOUR_VERY_STRONG_PASSWORD_HERE" or DB_PASSWORD in f.read():
                return jsonify({"success": False, "error": "SECURITY RISK: Change default password first."}), 400
    except FileNotFoundError:
        return jsonify({"success": False, "error": "docker-compose.yml not found."}), 500

    dump_command = (
        f"docker compose exec mongo mongodump "
        f"--username=root --password={shlex.quote(DB_PASSWORD)} "
        f"--authenticationDatabase=admin --archive={backup_file} --gzip"
    )
    result = run_command(dump_command)

    if result["success"] and os.path.exists(backup_file):
        try:
            return send_file(backup_file, as_attachment=True, download_name="mongo_backup.gz", mimetype="application/gzip")
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
        finally:
            if os.path.exists(backup_file):
                os.remove(backup_file)
    else:
        return jsonify(result), 500

@app.route('/logs', methods=['GET'])
def logs():
    result = run_command("docker compose logs --tail=50", get_output=True)
    return jsonify(result)

@app.route('/add-rule', methods=['POST'])
def add_rule():
    try:
        ip_address = request.json.get('ip')
        if not ip_address:
            return jsonify({"success": False, "error": "No IP address provided."}), 400
        safe_ip = shlex.quote(ip_address)
        command = f"sudo ufw allow from {safe_ip} to any port 27017 proto tcp"
        # Capture output for confirmation
        result = run_command(command, get_output=True)
        if not result["success"] and "ERROR:" in result.get("output", ""):
            result["error"] = result["output"]
        return jsonify(result)
    except Exception as e:
        print(f"Error in /add-rule: {e}")
        return jsonify({"success": False, "status": "error", "error": f"Server error: {str(e)}"}), 500

@app.route('/restore', methods=['POST'])
def restore():
    if 'backupFile' not in request.files:
        return jsonify({"success": False, "error": "No file part in request."}), 400
    file = request.files['backupFile']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected."}), 400

    if file:
        filename = secure_filename(file.filename)
        server_temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        container_temp_path = f"/tmp/{filename}"
        file.save(server_temp_path)

        copy_command = f"docker cp {shlex.quote(server_temp_path)} my-mongo-db:{shlex.quote(container_temp_path)}"
        copy_result = run_command(copy_command)
        if not copy_result["success"]:
            os.remove(server_temp_path) # Clean up server file on copy failure
            return jsonify(copy_result), 500

        restore_command = (
            f"docker compose exec mongo mongorestore "
            f"--username=root --password={shlex.quote(DB_PASSWORD)} "
            f"--authenticationDatabase=admin --archive={shlex.quote(container_temp_path)} --gzip --drop"
        )
        restore_result = run_command(restore_command)

        # Clean up temp files
        os.remove(server_temp_path)
        run_command(f"docker compose exec mongo rm {shlex.quote(container_temp_path)}")

        return jsonify(restore_result)
    return jsonify({"success": False, "error": "Unknown file upload error."}), 500

@app.route('/status', methods=['GET'])
def get_status():
    command = "docker inspect --format '{{.State.Status}}' my-mongo-db"
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        status = result.stdout.strip()
        return jsonify({"success": True, "status": status})
    except subprocess.CalledProcessError as e:
        if "No such object" in e.stderr:
            return jsonify({"success": True, "status": "not_deployed"})
        else:
            return jsonify({"success": False, "status": "error", "error": e.stderr})
    except Exception as e:
        return jsonify({"success": False, "status": "error", "error": str(e)})

# --- Run the App ---
if __name__ == '__main__':
    try:
        with open(os.path.join(PROJECT_DIR, 'docker-compose.yml'), 'r') as f:
            # Check against the actual password variable now
            if DB_PASSWORD == "YOUR_VERY_STRONG_PASSWORD_HERE" or DB_PASSWORD in f.read():
                print("="*60)
                print("WARNING: Default password detected.")
                print("Edit 'docker-compose.yml' and 'app.py' (top) for security.")
                print("="*60)
    except FileNotFoundError:
        print("Warning: docker-compose.yml not found.")

    app.run(host='0.0.0.0', port=5000, debug=False)