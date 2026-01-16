"""
Gemini Business 认证工具类
抽取注册和登录服务的公共逻辑，遵循 DRY 原则

艹，把重复代码都提取到这里了，别再写重复的SB代码了！
"""
import json
import time
import logging
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse, parse_qs
from datetime import datetime

import requests
import urllib3

from core.config import config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("gemini.auth_utils")


class GeminiAuthConfig:
    """认证配置类（从统一配置模块加载）"""

    def __init__(self):
        # 从统一配置模块读取
        self.mail_api = config.basic.mail_api
        self.admin_key = config.basic.mail_admin_key
        self.email_domains = config.basic.email_domain  # 改为数组
        self.google_mail = config.basic.google_mail
        self.login_url = config.security.login_url

    def validate(self) -> bool:
        """验证配置是否完整"""
        required = [self.mail_api, self.admin_key, self.google_mail, self.login_url]
        return all(required)


class GeminiAuthHelper:
    """Gemini 认证辅助工具"""

    # XPath 配置（公共）
    XPATH = {
        "email_input": "/html/body/c-wiz/div/div/div[1]/div/div/div/form/div[1]/div[1]/div/span[2]/input",
        "continue_btn": "/html/body/c-wiz/div/div/div[1]/div/div/div/form/div[2]/div/button",
        "verify_btn": "/html/body/c-wiz/div/div/div[1]/div/div/div/form/div[2]/div/div[1]/span/div[1]/button",
    }

    def __init__(self, config: GeminiAuthConfig):
        self.config = config

    def get_verification_code(self, email: str, timeout: int = 60) -> Optional[str]:
        """获取验证码（公共方法）"""
        logger.info(f"⏳ 等待验证码 [{email}]...")
        start = time.time()

        while time.time() - start < timeout:
            try:
                r = requests.get(
                    f"{self.config.mail_api}/admin/mails?limit=20&offset=0",
                    headers={"x-admin-auth": self.config.admin_key},
                    timeout=10,
                    verify=False
                )
                if r.status_code == 200:
                    emails = r.json().get('results', {})
                    for mail in emails:
                        if mail.get("address") == email and mail.get("source") == self.config.google_mail:
                            logger.info(f"📩 找到邮件 [{mail.get('id')}]，正在提取验证码...")
                            code = None
                            mail_id = mail.get("id")
                            
                            # 优先从 metadata 中获取验证码（AI 提取）
                            try:
                                metadata_str = mail.get("metadata")
                                if metadata_str:
                                    metadata = json.loads(metadata_str)
                                    if metadata and "ai_extract" in metadata and metadata["ai_extract"].get("result"):
                                        code = metadata["ai_extract"]["result"]
                                        logger.info(f"✅ 从 metadata 获取验证码: {code}")
                            except Exception as e:
                                logger.warning(f"⚠️ metadata 解析失败: {e}")
                            
                            # 如果 metadata 为空，从 raw 中提取验证码
                            if not code:
                                raw = mail.get("raw", "")
                                if raw:
                                    import re
                                    # Step 1: 去掉 quoted-printable 软换行（行尾的 = 表示续行）
                                    clean_raw = re.sub(r'=\r?\n', '', raw)
                                    
                                    # Step 2: 解码 quoted-printable 的 =XX（如 =3D 是 =）
                                    def decode_qp(match):
                                        hex_val = match.group(1)
                                        return chr(int(hex_val, 16))
                                    clean_raw = re.sub(r'=([0-9A-Fa-f]{2})', decode_qp, clean_raw)
                                    
                                    # Step 3: 去掉转义的引号
                                    clean_raw = clean_raw.replace('\\"', '"')
                                    
                                    # 优先匹配 HTML 中的 verification-code span 标签内容
                                    # 格式: <span class="verification-code" ...>SHCNXF</span>
                                    html_match = re.search(r'class\s*=\s*["\']?verification-code["\']?[^>]*>([A-Z0-9]{6})<', clean_raw, re.IGNORECASE)
                                    if html_match:
                                        code = html_match.group(1)
                                        logger.info(f"✅ 从 HTML span 提取验证码: {code}")
                                    else:
                                        # 备用：匹配验证码格式（6位大写字母+数字，前后有换行或特殊字符）
                                        text_match = re.search(r'(?:验证码[为是：:\s]*|verification code[:\s]*)[\r\n\s]*([A-Z0-9]{6})[\r\n\s]', clean_raw, re.IGNORECASE)
                                        if text_match:
                                            code = text_match.group(1)
                                            logger.info(f"✅ 从文本提取验证码: {code}")
                            
                            if code:
                                # 获取验证码后立即删除邮件，避免后续刷新时误取旧验证码
                                if mail_id:
                                    try:
                                        requests.delete(
                                            f"{self.config.mail_api}/admin/mails/{mail_id}",
                                            headers={"x-admin-auth": self.config.admin_key},
                                            timeout=10,
                                            verify=False
                                        )
                                        logger.info(f"🗑️ 已删除邮件 [{mail_id}]")
                                    except Exception as e:
                                        logger.warning(f"⚠️ 删除邮件失败 [{mail_id}]: {e}")
                                
                                return code
            except:
                pass
            time.sleep(2)

        logger.error(f"❌ 验证码超时 [{email}]")
        return None

    def perform_email_verification(self, driver, wait, email: str, max_retries: int = 3) -> Dict[str, Any]:
        """
        执行邮箱验证流程（公共方法）
        从输入邮箱到验证码验证完成

        如果验证码获取失败，会刷新页面重新尝试，最多重试 max_retries 次

        返回: {"success": bool, "error": str|None}
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC

        last_error = None

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    logger.info(f"🔄 第 {attempt + 1}/{max_retries} 次重试...")
                    # 刷新页面回到登录页
                    driver.get(self.config.login_url)
                    time.sleep(2)

                # 1. 输入邮箱（多种选择器备选）
                inp = None
                email_selectors = [
                    (By.XPATH, self.XPATH["email_input"]),
                    (By.CSS_SELECTOR, "input[type='email']"),
                    (By.CSS_SELECTOR, "input[name='identifier']"),
                    (By.CSS_SELECTOR, "input[autocomplete='email']"),
                ]
                for selector in email_selectors:
                    try:
                        inp = wait.until(EC.element_to_be_clickable(selector))
                        if inp:
                            logger.info(f"✅ 找到邮箱输入框: {selector}")
                            break
                    except:
                        continue

                if not inp:
                    last_error = "未找到邮箱输入框"
                    continue

                inp.click()
                inp.clear()
                for c in email:
                    inp.send_keys(c)
                    time.sleep(0.02)
                logger.info(f"✅ 邮箱已输入: {email}")

                # 2. 点击继续按钮（多种选择器备选）
                time.sleep(0.5)
                btn = None
                continue_selectors = [
                    (By.XPATH, self.XPATH["continue_btn"]),
                    (By.CSS_SELECTOR, "button[type='submit']"),
                    (By.XPATH, "//button[contains(text(), '继续')]"),
                    (By.XPATH, "//button[contains(text(), 'Continue')]"),
                    (By.XPATH, "//button[contains(text(), '下一步')]"),
                    (By.XPATH, "//button[contains(text(), 'Next')]"),
                ]
                for selector in continue_selectors:
                    try:
                        btn = wait.until(EC.element_to_be_clickable(selector))
                        if btn:
                            logger.info(f"✅ 找到继续按钮: {selector}")
                            break
                    except:
                        continue

                if not btn:
                    last_error = "未找到继续按钮"
                    continue

                # 使用 ActionChains 点击，更接近真实用户行为
                from selenium.webdriver.common.action_chains import ActionChains
                ActionChains(driver).move_to_element(btn).click().perform()
                logger.info(f"✅ 已点击继续按钮，等待验证码页面...")

                # 等待页面跳转到验证码输入页面（检测验证码输入框出现）
                time.sleep(2)
                try:
                    # 等待验证码输入框出现，最多等待10秒
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='pinInput'], span[data-index='0']")))
                    logger.info(f"✅ 验证码页面已加载")
                except:
                    # 检查是否出现错误页面
                    page_source = driver.page_source
                    if "请试试其他方法" in page_source or "格式不正确" in page_source:
                        logger.error(f"❌ Google 拒绝了登录请求（可能账户已被限制）")
                        return {"success": False, "error": "Google 拒绝登录请求，账户可能已被限制"}
                    logger.warning(f"⚠️ 未检测到验证码输入框，继续尝试获取验证码...")

                # 3. 获取验证码
                code = self.get_verification_code(email)
                if not code:
                    last_error = "验证码超时"
                    logger.warning(f"⚠️ 验证码获取失败，准备重试...")
                    continue  # 重试

                # 4. 输入验证码
                time.sleep(1)
                code_entered = False

                # 方法1: 智能定位验证码输入区域，模拟真人输入行为
                try:
                    from selenium.webdriver.common.action_chains import ActionChains
                    import random as _random

                    # 多种选择器备选，按优先级尝试
                    selectors = [
                        "span[data-index='0']",
                        "div[data-index='0']",
                        "input[data-index='0']",
                        "div.nwkWRe span:first-child",
                        "div[role='textbox']",
                    ]

                    target_element = None
                    for sel in selectors:
                        try:
                            target_element = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
                            if target_element.is_displayed():
                                logger.info(f"📍 找到验证码输入区域: {sel}")
                                break
                        except:
                            continue

                    if not target_element:
                        raise Exception("未找到验证码输入区域")

                    # 模拟真人：先移动鼠标到元素附近，再点击
                    actions = ActionChains(driver)
                    actions.move_to_element(target_element).pause(_random.uniform(0.1, 0.3)).click().perform()
                    time.sleep(_random.uniform(0.3, 0.6))

                    # 获取当前焦点元素
                    active = driver.switch_to.active_element

                    # 模拟真人打字：随机延迟 + 偶尔停顿
                    for i, char in enumerate(code):
                        active.send_keys(char)

                        # 基础延迟 80-180ms（更接近真人打字速度）
                        delay = _random.uniform(0.08, 0.18)

                        # 5% 概率额外停顿（模拟思考或看屏幕）
                        if _random.random() < 0.05:
                            delay += _random.uniform(0.2, 0.5)

                        time.sleep(delay)

                    code_entered = True
                    logger.info(f"✅ 验证码输入成功（方法1: 智能定位+真人模拟）")
                except Exception as e1:
                    logger.warning(f"⚠️ 方法1失败: {e1}")

                # 方法2: 点击隐藏的 input 元素，然后逐字符发送
                if not code_entered:
                    try:
                        pin = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='pinInput']")))
                        # 使用 ActionChains 点击并聚焦
                        from selenium.webdriver.common.action_chains import ActionChains
                        ActionChains(driver).move_to_element(pin).click().perform()
                        time.sleep(0.3)
                        active = driver.switch_to.active_element
                        for char in code:
                            active.send_keys(char)
                            time.sleep(0.05 + 0.05 * __import__('random').random())
                        code_entered = True
                        logger.info(f"✅ 验证码输入成功（方法2: input点击+逐字符）")
                    except Exception as e2:
                        logger.warning(f"⚠️ 方法2失败: {e2}")

                # 方法3: 点击容器后发送按键
                if not code_entered:
                    try:
                        container = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.nwkWRe")))
                        container.click()
                        time.sleep(0.3)
                        active = driver.switch_to.active_element
                        for char in code:
                            active.send_keys(char)
                            time.sleep(0.05 + 0.05 * __import__('random').random())
                        code_entered = True
                        logger.info(f"✅ 验证码输入成功（方法3: 容器点击+逐字符）")
                    except Exception as e3:
                        logger.warning(f"⚠️ 方法3失败: {e3}")

                if not code_entered:
                    last_error = "验证码输入失败: 所有方法均失败"
                    continue  # 重试

                # 5. 点击验证按钮
                time.sleep(0.5)
                verify_clicked = False

                # 方法1: 使用 XPath 找验证按钮
                try:
                    vbtn = wait.until(EC.element_to_be_clickable((By.XPATH, self.XPATH["verify_btn"])))
                    from selenium.webdriver.common.action_chains import ActionChains
                    ActionChains(driver).move_to_element(vbtn).click().perform()
                    verify_clicked = True
                    logger.info("✅ 点击验证按钮成功（方法1: XPath）")
                except Exception as e1:
                    logger.warning(f"⚠️ 验证按钮方法1失败: {e1}")

                # 方法2: 查找包含"验证"文字的按钮
                if not verify_clicked:
                    try:
                        from selenium.webdriver.common.action_chains import ActionChains
                        for btn in driver.find_elements(By.TAG_NAME, "button"):
                            btn_text = btn.text.lower()
                            if '验证' in btn_text or 'verify' in btn_text:
                                ActionChains(driver).move_to_element(btn).click().perform()
                                verify_clicked = True
                                logger.info(f"✅ 点击验证按钮成功（方法2: 文字匹配 '{btn.text}'）")
                                break
                    except Exception as e2:
                        logger.warning(f"⚠️ 验证按钮方法2失败: {e2}")

                # 方法3: 查找 type=submit 的按钮
                if not verify_clicked:
                    try:
                        submit_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']")))
                        from selenium.webdriver.common.action_chains import ActionChains
                        ActionChains(driver).move_to_element(submit_btn).click().perform()
                        verify_clicked = True
                        logger.info("✅ 点击验证按钮成功（方法3: submit按钮）")
                    except Exception as e3:
                        logger.warning(f"⚠️ 验证按钮方法3失败: {e3}")

                # 方法4: 模拟回车键提交
                if not verify_clicked:
                    try:
                        from selenium.webdriver.common.keys import Keys
                        driver.switch_to.active_element.send_keys(Keys.ENTER)
                        verify_clicked = True
                        logger.info("✅ 点击验证按钮成功（方法4: 回车键）")
                    except Exception as e4:
                        logger.warning(f"⚠️ 验证按钮方法4失败: {e4}")

                if not verify_clicked:
                    last_error = "验证按钮点击失败"
                    logger.error("❌ 所有验证按钮点击方法均失败")
                    continue  # 重试

                # 等待页面跳转
                time.sleep(2)

                # 验证成功
                return {"success": True, "error": None}

            except Exception as e:
                last_error = str(e)
                logger.warning(f"⚠️ 第 {attempt + 1} 次尝试失败: {e}")
                continue

        # 所有重试都失败
        logger.error(f"❌ 验证流程失败，已重试 {max_retries} 次: {last_error}")
        return {"success": False, "error": f"验证失败（已重试{max_retries}次）: {last_error}"}

    def extract_config_from_workspace(self, driver) -> Dict[str, Any]:
        """
        从工作台页面提取配置信息（公共方法）

        返回: {"success": bool, "config": dict|None, "error": str|None}
        """
        try:
            time.sleep(3)  # 等待页面完全加载
            cookies = driver.get_cookies()
            url = driver.current_url
            parsed = urlparse(url)

            # 解析 config_id
            path_parts = url.split('/')
            config_id = None
            for i, p in enumerate(path_parts):
                if p == 'cid' and i + 1 < len(path_parts):
                    config_id = path_parts[i + 1].split('?')[0]
                    break

            cookie_dict = {c['name']: c for c in cookies}
            ses_cookie = cookie_dict.get('__Secure-C_SES', {})
            host_cookie = cookie_dict.get('__Host-C_OSES', {})
            csesidx = parse_qs(parsed.query).get('csesidx', [None])[0]

            if not all([ses_cookie.get('value'), host_cookie.get('value'), csesidx, config_id]):
                return {"success": False, "config": None, "error": "配置数据不完整"}

            config_data = {
                "csesidx": csesidx,
                "config_id": config_id,
                "secure_c_ses": ses_cookie.get('value'),
                "host_c_oses": host_cookie.get('value'),
                "expires_at": datetime.fromtimestamp(
                    ses_cookie.get('expiry', 0) - 43200
                ).strftime('%Y-%m-%d %H:%M:%S') if ses_cookie.get('expiry') else None
            }

            return {"success": True, "config": config_data, "error": None}

        except Exception as e:
            return {"success": False, "config": None, "error": str(e)}

    def wait_for_workspace(self, driver, timeout: int = 30, max_crash_retries: int = 3) -> bool:
        """
        等待进入工作台（公共方法，带崩溃重试）

        Args:
            driver: Selenium WebDriver 实例
            timeout: 等待超时时间（秒）
            max_crash_retries: 崩溃后最大重试次数
            
        返回: True 表示成功进入，False 表示超时或失败
        """
        crash_count = 0
        workspace_url = "https://business.gemini.google/"
        
        for _ in range(timeout):
            time.sleep(1)
            try:
                # 检查页面是否崩溃
                page_source = driver.page_source
                is_crashed = 'crashed' in page_source.lower() or 'aw, snap' in page_source.lower()
                
                if is_crashed:
                    crash_count += 1
                    logger.warning(f"⚠️ 等待工作台时页面崩溃，尝试开新标签页 (崩溃 {crash_count}/{max_crash_retries})")
                    if crash_count >= max_crash_retries:
                        logger.error("❌ 页面崩溃次数过多，放弃重试")
                        return False
                    
                    # 开新标签页并切换
                    if self._recover_from_crash(driver, workspace_url):
                        time.sleep(3)
                        continue
                    else:
                        return False
                
                url = driver.current_url
                if 'business.gemini.google' in url and '/cid/' in url:
                    return True
                    
            except Exception as e:
                error_msg = str(e).lower()
                if 'crash' in error_msg or 'tab' in error_msg or 'target window' in error_msg:
                    crash_count += 1
                    logger.warning(f"⚠️ 等待工作台时检测到崩溃: {e} (崩溃 {crash_count}/{max_crash_retries})")
                    if crash_count >= max_crash_retries:
                        logger.error("❌ 页面崩溃次数过多，放弃重试")
                        return False
                    
                    if self._recover_from_crash(driver, workspace_url):
                        time.sleep(3)
                        continue
                    else:
                        return False
                # 其他异常继续等待
                
        return False
    
    def _recover_from_crash(self, driver, target_url: str) -> bool:
        """
        从崩溃中恢复：开新标签页访问目标URL

        艹，崩溃的标签页刷新没用，得开新的！
        """
        try:
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.common.action_chains import ActionChains

            # 获取当前所有窗口句柄
            original_handles = driver.window_handles

            # 使用快捷键打开新标签页 (Ctrl+T)
            ActionChains(driver).key_down(Keys.CONTROL).send_keys('t').key_up(Keys.CONTROL).perform()
            time.sleep(0.5)
            
            # 获取新窗口句柄
            new_handles = driver.window_handles
            new_handle = None
            for handle in new_handles:
                if handle not in original_handles:
                    new_handle = handle
                    break
            
            if not new_handle:
                logger.error("❌ 无法创建新标签页")
                return False
            
            # 切换到新标签页
            driver.switch_to.window(new_handle)
            
            # 关闭旧的崩溃标签页
            for handle in original_handles:
                try:
                    driver.switch_to.window(handle)
                    driver.close()
                except:
                    pass
            
            # 切回新标签页
            driver.switch_to.window(new_handle)
            
            # 访问目标URL
            driver.get(target_url)
            time.sleep(3)
            
            logger.info("✅ 已通过新标签页恢复")
            return True
            
        except Exception as e:
            logger.error(f"❌ 恢复失败: {e}")
            return False

    def extract_config_with_retry(self, driver, max_retries: int = 3) -> Dict[str, Any]:
        """
        带重试机制的配置提取（处理 tab crashed 问题）
        
        艹，Google 工作台页面经常崩溃，这个方法会自动重试
        
        Args:
            driver: Selenium WebDriver 实例
            max_retries: 最大重试次数，默认3次
            
        返回: {"success": bool, "config": dict|None, "error": str|None}
        """
        extract_result = None
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # 检查页面是否崩溃
                page_source = driver.page_source
                if 'crashed' in page_source.lower() or 'aw, snap' in page_source.lower():
                    logger.warning(f"⚠️ 页面崩溃，尝试刷新 (尝试 {attempt + 1}/{max_retries})")
                    driver.refresh()
                    time.sleep(3)
                    continue
                
                extract_result = self.extract_config_from_workspace(driver)
                if extract_result["success"]:
                    return extract_result
                else:
                    last_error = extract_result["error"]
                    logger.warning(f"⚠️ 提取配置失败: {last_error}，尝试刷新 (尝试 {attempt + 1}/{max_retries})")
                    driver.refresh()
                    time.sleep(3)
                    
            except Exception as e:
                error_msg = str(e).lower()
                if 'crash' in error_msg or 'tab' in error_msg:
                    logger.warning(f"⚠️ 检测到页面崩溃: {e}，尝试刷新 (尝试 {attempt + 1}/{max_retries})")
                    try:
                        driver.refresh()
                        time.sleep(3)
                    except:
                        # 如果刷新也失败，尝试重新访问工作台
                        try:
                            driver.get("https://business.gemini.google/")
                            time.sleep(5)
                        except:
                            pass
                else:
                    last_error = str(e)
                    logger.warning(f"⚠️ 提取配置异常: {e}，尝试刷新 (尝试 {attempt + 1}/{max_retries})")
                    try:
                        driver.refresh()
                        time.sleep(3)
                    except:
                        pass
        
        return {"success": False, "config": None, "error": last_error or "提取配置失败（已重试）"}

