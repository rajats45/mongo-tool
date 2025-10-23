import subprocess
import os
import shlex  # For safe command argument building
from flask import Flask, render_template, jsonify, request, send_file, abort

# Get the absolute path of the directory where this script is
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)

# --- Helper Function ---
def run_command(command, get_output=False):
    """A helper to run shell commands safely."""
    try:
        if get_output:
            # Run and capture output
            result = subprocess.run(
                command,
                shell=True,
                check=True,
                capture_output=True,
                text=True,
                cwd=PROJECT_DIR  # Run command in our project directory
            )
            return {"success": True, "output": result.stdout, "error": result.stderr}
        else:
            # Just run the command
            subprocess.run(command, shell=True, check=True, cwd=PROJECT_DIR)
            return {"success": True, "output": "Command executed successfully."}
    
    except subprocess.CalledProcessError as e:
        # If the command fails, return the error
        return {"success": False, "output": e.stdout, "error": e.stderr}
    except Exception as e:
        return {"success": False, "error": str(e)}

# --- 1. Main Page Route ---
@app.route('/')
def index():
    """Serves the main HTML page."""
    # 'index.html' will be the name of our GUI file
    return render_template('index.html')

# --- 2. Deployment / Update Route ---
@app.route('/deploy', methods=['POST'])
def deploy():
    """Pulls the latest image and starts the container."""
    # First, pull the latest image
    run_command("docker compose pull")
    # Then, start the container (this also applies updates)
    result = run_command("docker compose up -d")
    return jsonify(result)

# --- 3. Backup Route ---
@app.route('/backup', methods=['POST'])
def backup():
    """Runs mongodump and sends the backup file for download."""
    backup_file = "/tmp/mongo_backup.gz"
    
    # !! IMPORTANT: CHANGE THIS PASSWORD !!
    # This must match the password in your docker-compose.yml
    password = "YOUR_VERY_STRONG_PASSWORD_HERE" 
    
    # Check if the compose file has the default password
    try:
        with open(os.path.join(PROJECT_DIR, 'docker-compose.yml'), 'r') as f:
            if "YOUR_VERY_STRONG_PASSWORD_HERE" in f.read():
                 return jsonify({"success": False, "error": "SECURITY RISK: Please change the default password in your docker-compose.yml file first."}), 400
    except FileNotFoundError:
        return jsonify({"success": False, "error": "docker-compose.yml not found."}), 500

    
    dump_command = (
        f"docker compose exec mongo mongodump "
        f"--username=root --password={shlex.quote(password)} "
        f"--authenticationDatabase=admin "
        f"--archive={backup_file} --gzip"
    )
    
    result = run_command(dump_command)
    
    if result["success"] and os.path.exists(backup_file):
        try:
            return send_file(
                backup_file,
                as_attachment=True,
                download_name="mongo_backup.gz",
                mimetype="application/gzip"
            )
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
        finally:
            # Clean up the temp file after sending
            if os.path.exists(backup_file):
                os.remove(backup_file)
    else:
        # If dump failed, send the error
        return jsonify(result), 500

# --- 4. Logs Route ---
@app.route('/logs', methods=['GET'])
def logs():
    """Gets the last 50 lines of logs."""
    result = run_command("docker compose logs --tail=50", get_output=True)
    return jsonify(result)

# --- 5. Security (Firewall) Route ---
@app.route('/add-rule', methods=['POST'])
def add_rule():
    """Adds a UFW rule. REQUIRES SUDO."""
    ip_address = request.json.get('ip')
    if not ip_address:
        return jsonify({"success": False, "error": "No IP address provided."}), 400
    
    # Use shlex.quote to prevent command injection
    safe_ip = shlex.quote(ip_address)
    
    # This command uses the sudo permission we set up in install.sh
    command = f"sudo ufw allow from {safe_ip} to any port 27017 proto tcp"
    result = run_command(command)
    return jsonify(result)

# --- Run the App ---
if __name__ == '__main__':
    # Check if default password is still in compose file
    try:
        with open(os.path.join(PROJECT_DIR, 'docker-compose.yml'), 'r') as f:
            if "YOUR_VERY_STRONG_PASSWORD_HERE" in f.read():
                print("="*60)
                print("WARNING: You are using the default password.")
                print("Please edit 'docker-compose.yml' and 'app.py' to set a secure password.")
                print("="*60)
    except FileNotFoundError:
        print("Warning: docker-compose.yml not found. Cannot check for default password.")

    # Host=0.0.0.0 makes it accessible from your server's public IP
    # debug=False is safer for a "production" tool
    app.run(host='0.0.0.0', port=5000, debug=False)