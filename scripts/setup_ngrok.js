#!/usr/bin/env node
/**
 * Automatic Ngrok Download and Setup Script
 * Downloads ngrok and starts tunnel for local agent
 */

const https = require('https');
const fs = require('fs');
const path = require('path');
const { exec, spawn } = require('child_process');
const os = require('os');

function getNgrokDownloadUrl() {
    const platform = os.platform();
    const arch = os.arch();
    
    if (platform === 'win32') {
        if (arch === 'x64') {
            return 'https://bin.equinox.io/c/4VmDzA7WQbg/ngrok-stable-windows-amd64.zip';
        } else {
            return 'https://bin.equinox.io/c/4VmDzA7WQbg/ngrok-stable-windows-386.zip';
        }
    } else if (platform === 'darwin') {
        if (arch === 'arm64') {
            return 'https://bin.equinox.io/c/4VmDzA7WQbg/ngrok-stable-darwin-arm64.zip';
        } else {
            return 'https://bin.equinox.io/c/4VmDzA7WQbg/ngrok-stable-darwin-amd64.zip';
        }
    } else if (platform === 'linux') {
        if (arch === 'arm64') {
            return 'https://bin.equinox.io/c/4VmDzA7WQbg/ngrok-stable-linux-arm64.zip';
        } else {
            return 'https://bin.equinox.io/c/4VmDzA7WQbg/ngrok-stable-linux-amd64.zip';
        }
    } else {
        throw new Error(`Unsupported platform: ${platform}`);
    }
}

function downloadNgrok() {
    return new Promise((resolve, reject) => {
        console.log('Downloading ngrok...');
        
        const url = getNgrokDownloadUrl();
        const filename = url.split('/').pop();
        const scriptsDir = __dirname;
        const ngrokPath = path.join(scriptsDir, filename);
        
        const file = fs.createWriteStream(ngrokPath);
        
        https.get(url, (response) => {
            if (response.statusCode !== 200) {
                reject(new Error(`Failed to download ngrok: ${response.statusCode}`));
                return;
            }
            
            response.pipe(file);
            
            file.on('finish', () => {
                console.log(`Downloaded: ${filename}`);
                extractNgrok(ngrokPath, scriptsDir).then(resolve).catch(reject);
            });
        }).on('error', (err) => {
            fs.unlink(ngrokPath, () => {});
            reject(err);
        });
    });
}

function extractNgrok(zipPath, scriptsDir) {
    return new Promise((resolve, reject) => {
        console.log('Extracting ngrok...');
        
        const unzip = require('unzipper');
        
        unzip.createReadStream(zipPath)
            .pipe(unzip.Extract({ path: scriptsDir }))
            .on('close', () => {
                fs.unlinkSync(zipPath);
                
                const ngrokExe = os.platform() === 'win32' 
                    ? path.join(scriptsDir, 'ngrok.exe')
                    : path.join(scriptsDir, 'ngrok');
                
                if (fs.existsSync(ngrokExe)) {
                    if (os.platform() !== 'win32') {
                        fs.chmodSync(ngrokExe, '755');
                    }
                    console.log(`Ngrok installed at: ${ngrokExe}`);
                    resolve(ngrokExe);
                } else {
                    reject(new Error('Ngrok executable not found after extraction'));
                }
            })
            .on('error', reject);
    });
}

function startNgrok(ngrokPath, port = 8088) {
    return new Promise((resolve, reject) => {
        console.log(`Starting ngrok tunnel for port ${port}...`);
        
        const ngrok = spawn(ngrokPath, ['http', port.toString()], {
            stdio: 'ignore',
            detached: true
        });
        
        ngrok.unref();
        
        // Wait for ngrok to start
        setTimeout(() => {
            getNgrokUrlFromAPI().then((ngrokUrl) => {
                console.log(`Ngrok tunnel started: ${ngrokUrl}`);
                console.log(`Local: http://localhost:${port} -> Remote: ${ngrokUrl}`);
                saveNgrokUrl(ngrokUrl);
                resolve({ ngrokUrl, process: ngrok });
            }).catch(reject);
        }, 3000);
    });
}

function getNgrokUrlFromAPI() {
    return new Promise((resolve, reject) => {
        https.get('http://localhost:4040/api/tunnels', (res) => {
            let data = '';
            
            res.on('data', (chunk) => {
                data += chunk;
            });
            
            res.on('end', () => {
                try {
                    const parsed = JSON.parse(data);
                    if (parsed.tunnels && parsed.tunnels.length > 0) {
                        resolve(parsed.tunnels[0].public_url);
                    } else {
                        reject(new Error('No ngrok tunnels found'));
                    }
                } catch (err) {
                    reject(err);
                }
            });
        }).on('error', reject);
    });
}

function saveNgrokUrl(ngrokUrl) {
    const urlFile = path.join(__dirname, 'ngrok_url.txt');
    fs.writeFileSync(urlFile, ngrokUrl);
    console.log(`Ngrok URL saved to: ${urlFile}`);
}

function getNgrokUrl() {
    const urlFile = path.join(__dirname, 'ngrok_url.txt');
    if (fs.existsSync(urlFile)) {
        return fs.readFileSync(urlFile, 'utf-8').trim();
    }
    return null;
}

async function main() {
    try {
        const scriptsDir = __dirname;
        const ngrokExe = os.platform() === 'win32' 
            ? path.join(scriptsDir, 'ngrok.exe')
            : path.join(scriptsDir, 'ngrok');
        
        if (!fs.existsSync(ngrokExe)) {
            await downloadNgrok();
        } else {
            console.log(`Ngrok already installed at: ${ngrokExe}`);
        }
        
        const { ngrokUrl } = await startNgrok(ngrokExe, 8088);
        
        console.log('\nNgrok is running. Press Ctrl+C to stop.');
        console.log(`Use this URL in Render: ${ngrokUrl}`);
        
        // Handle graceful shutdown
        process.on('SIGINT', () => {
            console.log('\nStopping ngrok...');
            // Kill ngrok process (detached, so this is just for cleanup)
            if (os.platform() === 'win32') {
                exec('taskkill /F /IM ngrok.exe');
            } else {
                exec('pkill ngrok');
            }
            console.log('Ngrok stopped.');
            process.exit(0);
        });
        
    } catch (error) {
        console.error('Error:', error.message);
        process.exit(1);
    }
}

if (require.main === module) {
    main();
}
