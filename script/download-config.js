// ==UserScript==
// @name         Gemini Business 2API Helper
// @namespace    https://linux.do/u/f-droid
// @version      1.0
// @icon         https://cdn.inviter.co/community/b5c3dc29-b7e3-49f9-a18d-819398ba4fe6.png
// @description  提取 Gemini Business 配置，支持编辑、一键复制。
// @author       Gemini Business
// @match        https://business.gemini.google/*
// @grant        GM_setClipboard
// @grant        GM_addStyle
// @grant        GM_cookie
// @connect      business.gemini.google
// ==/UserScript==

(function () {
    'use strict';

    const getFavicon = () => {
        const link = document.querySelector("link[rel*='icon']") || document.querySelector("link[rel='shortcut icon']");
        return link ? link.href : 'https://cdn.inviter.co/community/b5c3dc29-b7e3-49f9-a18d-819398ba4fe6.png';
    };

    GM_addStyle(`
        :root {
            --gb-primary: #1a73e8;
            --gb-primary-hover: #1557b0;
            --gb-success: #1e8e3e;
            --gb-success-hover: #137333;
            --gb-surface: #ffffff;
            --gb-bg: #f8f9fa;
            --gb-text-main: #202124;
            --gb-text-sub: #5f6368;
            --gb-border: #dadce0;
            --gb-shadow-sm: 0 1px 2px 0 rgba(60,64,67,0.3), 0 1px 3px 1px rgba(60,64,67,0.15);
            --gb-shadow-md: 0 4px 8px 3px rgba(60,64,67,0.15), 0 1px 3px rgba(60,64,67,0.3);
            --gb-shadow-lg: 0 8px 24px rgba(60,64,67,0.2);
            --gb-font: 'Google Sans', 'Roboto', Arial, sans-serif;
            --gb-mono: 'Roboto Mono', 'Menlo', monospace;
            --transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        }

        #gb-float-ball {
            position: fixed;
            bottom: 32px;
            right: 32px;
            width: 60px;
            height: 60px;
            background: white;
            border-radius: 50%;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
            cursor: pointer;
            z-index: 9998;
            border: 1px solid var(--gb-border);
            display: flex;
            align-items: center;
            justify-content: center;
            transition: var(--transition);
            transform: scale(1);
        }

        #gb-float-ball:hover {
            transform: scale(1.1) rotate(10deg);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
        }

        #gb-float-ball img {
            width: 36px;
            height: 36px;
            border-radius: 8px;
            object-fit: contain;
            pointer-events: none;
        }

        #gb-float-ball::after {
            content: '2API';
            position: absolute;
            bottom: -4px;
            right: -4px;
            font-size: 8px;
            font-weight: bold;
            background: var(--gb-primary);
            color: white;
            padding: 2px 6px;
            border-radius: 8px;
            transform: rotate(-15deg);
        }

        #gb-overlay {
            position: fixed; inset: 0;
            background: rgba(32, 33, 36, 0.6);
            backdrop-filter: blur(3px);
            z-index: 9999;
            display: flex; align-items: center; justify-content: center;
            opacity: 0; pointer-events: none;
            transition: opacity 0.25s ease;
        }
        #gb-overlay.active { opacity: 1; pointer-events: auto; }

        #gb-panel {
            width: 520px; max-width: 90vw;
            background: var(--gb-surface);
            border-radius: 24px;
            box-shadow: var(--gb-shadow-lg);
            overflow: hidden;
            display: flex; flex-direction: column;
            transform: scale(0.92) translateY(20px);
            transition: transform 0.3s cubic-bezier(0.2, 0.0, 0, 1);
            font-family: var(--gb-font);
        }
        #gb-overlay.active #gb-panel { transform: scale(1) translateY(0); }

        .gb-header {
            background: linear-gradient(135deg, #4285f4 0%, #34a853 100%);
            padding: 24px 32px;
            color: white;
        }
        .gb-title { font-size: 22px; font-weight: 500; margin: 0; letter-spacing: 0.5px; }
        .gb-subtitle { font-size: 13px; opacity: 0.9; margin-top: 6px; font-weight: 400; }

        .gb-body { padding: 24px 32px 16px; background: var(--gb-surface); }
        .gb-label {
            font-size: 14px; color: var(--gb-text-sub);
            margin-bottom: 12px; font-weight: 500;
            display: flex; justify-content: space-between; align-items: center;
        }

        .gb-textarea-wrapper {
            position: relative;
            border: 1px solid var(--gb-border);
            border-radius: 12px;
            background: var(--gb-bg);
            transition: border-color 0.2s, background 0.2s;
        }
        .gb-textarea-wrapper.editing {
            background: white;
            border-color: var(--gb-primary);
            box-shadow: 0 0 0 2px rgba(26, 115, 232, 0.2);
        }
        .gb-textarea {
            width: 100%; height: 220px;
            border: none; background: transparent;
            padding: 16px;
            font-family: var(--gb-mono);
            font-size: 13px; line-height: 1.6;
            color: var(--gb-text-main);
            resize: none; outline: none;
            box-sizing: border-box;
        }

        .gb-status {
            margin-top: 12px; font-size: 13px;
            display: flex; align-items: center; gap: 8px;
            color: var(--gb-text-sub);
            height: 20px;
        }
        .gb-dot { width: 8px; height: 8px; border-radius: 50%; background: #ccc; transition: background 0.3s; }
        .gb-dot.success { background: var(--gb-success); }
        .gb-dot.error { background: #ea4335; }

        .gb-footer {
            padding: 16px 32px 24px;
            display: flex; justify-content: flex-end; gap: 12px;
            border-top: 1px solid #f1f3f4;
            background: var(--gb-surface);
        }

        .gb-btn {
            border: none; outline: none;
            padding: 0 24px; height: 40px;
            border-radius: 20px;
            font-family: var(--gb-font);
            font-size: 14px; font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            display: flex; align-items: center; justify-content: center;
        }
        .gb-btn-text {
            background: transparent; color: var(--gb-text-sub);
        }
        .gb-btn-text:hover { background: rgba(0,0,0,0.05); color: var(--gb-text-main); }

        .gb-btn-primary {
            background: var(--gb-primary); color: white;
            box-shadow: var(--gb-shadow-sm);
        }
        .gb-btn-primary:hover {
            background: var(--gb-primary-hover);
            box-shadow: var(--gb-shadow-md);
        }
        .gb-btn-primary:active { transform: scale(0.98); }

        .gb-btn-success {
            background: var(--gb-success); color: white;
        }
        .gb-btn-success:hover { background: var(--gb-success-hover); }

        .gb-hidden { display: none !important; }
    `);

    const floatBall = document.createElement('div');
    floatBall.id = 'gb-float-ball';
    floatBall.title = "提取配置";
    const ballIcon = document.createElement('img');
    ballIcon.src = getFavicon();
    floatBall.appendChild(ballIcon);
    document.body.appendChild(floatBall);

    const overlay = document.createElement('div');
    overlay.id = 'gb-overlay';
    const panel = document.createElement('div');
    panel.id = 'gb-panel';
    overlay.appendChild(panel);
    document.body.appendChild(overlay);

    const header = document.createElement('div');
    header.className = 'gb-header';
    const title = document.createElement('h2');
    title.className = 'gb-title';
    title.textContent = 'Gemini Business 2API Helper';
    const subtitle = document.createElement('div');
    subtitle.className = 'gb-subtitle';
    subtitle.textContent = '配置提取与管理';
    header.appendChild(title);
    header.appendChild(subtitle);
    panel.appendChild(header);

    const body = document.createElement('div');
    body.className = 'gb-body';

    const label = document.createElement('div');
    label.className = 'gb-label';
    label.textContent = '提取的 .env 配置：';
    body.appendChild(label);

    const textWrapper = document.createElement('div');
    textWrapper.className = 'gb-textarea-wrapper';
    const textarea = document.createElement('textarea');
    textarea.className = 'gb-textarea';
    textarea.readOnly = true;
    textarea.spellcheck = false;
    textWrapper.appendChild(textarea);
    body.appendChild(textWrapper);

    const statusDiv = document.createElement('div');
    statusDiv.className = 'gb-status';
    const statusDot = document.createElement('div');
    statusDot.className = 'gb-dot';
    const statusText = document.createElement('span');
    statusText.textContent = '等待操作...';
    statusDiv.appendChild(statusDot);
    statusDiv.appendChild(statusText);
    body.appendChild(statusDiv);
    panel.appendChild(body);

    const footer = document.createElement('div');
    footer.className = 'gb-footer';

    const btnClose = document.createElement('button');
    btnClose.className = 'gb-btn gb-btn-text';
    btnClose.textContent = '关闭';

    const btnEdit = document.createElement('button');
    btnEdit.className = 'gb-btn gb-btn-text';
    btnEdit.textContent = '编辑';

    const btnSave = document.createElement('button');
    btnSave.className = 'gb-btn gb-btn-success gb-hidden';
    btnSave.textContent = '保存修改';

    const btnCopy = document.createElement('button');
    btnCopy.className = 'gb-btn gb-btn-primary';
    btnCopy.textContent = '复制配置';

    footer.appendChild(btnClose);
    footer.appendChild(btnEdit);
    footer.appendChild(btnSave);
    footer.appendChild(btnCopy);
    panel.appendChild(footer);

    let isEditing = false;
    let extractedData = "";

    const formatTime = (ts) => {
        if (!ts) return null;
        const d = new Date((ts - 43200) * 1000);
        return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
    };

    const setStatus = (type, msg) => {
        statusDot.className = 'gb-dot ' + (type === 'success' ? 'success' : type === 'error' ? 'error' : '');
        statusText.textContent = msg;
    };

    const toggleEditMode = () => {
        isEditing = !isEditing;
        textarea.readOnly = !isEditing;

        if (isEditing) {
            textWrapper.classList.add('editing');
            btnEdit.classList.add('gb-hidden');
            btnCopy.classList.add('gb-hidden');
            btnSave.classList.remove('gb-hidden');
            setStatus('normal', '正在编辑...');
            textarea.focus();
        } else {
            textWrapper.classList.remove('editing');
            btnEdit.classList.remove('gb-hidden');
            btnCopy.classList.remove('gb-hidden');
            btnSave.classList.add('gb-hidden');
        }
    };

    const saveContent = () => {
        extractedData = textarea.value;
        toggleEditMode();
        setStatus('success', '修改已保存');
    };

    const openPanel = () => {
        overlay.classList.add('active');

        textarea.value = "正在读取环境数据...";
        textarea.style.color = "#9aa0a6";
        btnCopy.disabled = true;
        btnEdit.style.display = 'none';
        setStatus('normal', '分析中...');

        const pathParts = window.location.pathname.split('/');
        const cidIndex = pathParts.indexOf('cid');
        const config_id = (cidIndex !== -1 && pathParts.length > cidIndex + 1) ? pathParts[cidIndex + 1] : null;
        const urlParams = new URLSearchParams(window.location.search);
        const csesidx = urlParams.get('csesidx');

        GM_cookie('list', {}, (cookies, error) => {
            if (error) {
                textarea.value = "错误：无法读取 Cookie。\n请检查 Tampermonkey 权限。";
                textarea.style.color = "#ea4335";
                setStatus('error', '读取失败');
                return;
            }

            const host_c_oses = (cookies.find(c => c.name === '__Host-C_OSES' && c.domain === window.location.hostname) || {}).value || null;
            const sesCookie = cookies.find(c => c.name === '__Secure-C_SES') || {};
            const secure_c_ses = sesCookie.value || null;

            if (!config_id || !csesidx || !secure_c_ses) {
                textarea.value = "⚠️ 数据不完整。\n请确保您在 Gemini Business 聊天界面，且 URL 包含 /cid/ 和 ?csesidx=";
                textarea.style.color = "#f9ab00";
                setStatus('error', '数据缺失');
                return;
            }

            // 获取或输入 email
            let email = localStorage.getItem('gemini_user_email');
            if (!email) {
                email = prompt('请输入您的邮箱地址：');
                if (email) {
                    localStorage.setItem('gemini_user_email', email);
                }
            }

            // 构建 JSON 格式的数据对象，与 download-config.js 保持一致
            const data = {
                id: email || 'unknown',
                csesidx,
                config_id,
                secure_c_ses,
                host_c_oses,
                expires_at: formatTime(sesCookie.expirationDate)
            };

            extractedData = JSON.stringify(data, null, 2);
            textarea.value = extractedData;
            textarea.style.color = "var(--gb-text-main)";
            btnCopy.disabled = false;
            btnEdit.style.display = 'block';
            setStatus('success', '提取成功');
        });
    };

    const closePanel = () => {
        overlay.classList.remove('active');
        if (isEditing) {
            textarea.value = extractedData;
            toggleEditMode();
        }
    };

    const copyToClipboard = () => {
        if (!textarea.value) return;
        GM_setClipboard(textarea.value);

        const originalText = btnCopy.textContent;
        btnCopy.textContent = "已复制";
        btnCopy.classList.remove('gb-btn-primary');
        btnCopy.classList.add('gb-btn-success');

        setTimeout(() => {
            btnCopy.textContent = originalText;
            btnCopy.classList.remove('gb-btn-success');
            btnCopy.classList.add('gb-btn-primary');
            closePanel();
        }, 1200);
    };

    floatBall.addEventListener('click', openPanel);
    btnClose.addEventListener('click', closePanel);
    btnCopy.addEventListener('click', copyToClipboard);
    btnEdit.addEventListener('click', toggleEditMode);
    btnSave.addEventListener('click', saveContent);

    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closePanel();
    });

})();