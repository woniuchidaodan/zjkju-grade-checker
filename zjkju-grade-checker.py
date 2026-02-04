import sys
import json
import time
import os
import logging
import requests
import hashlib
import threading
import smtplib
import ssl
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr


# 检查并安装必要的库
def check_and_install_dependencies():
    """检查并安装必要的依赖库"""
    required_libraries = [
        ('selenium', 'selenium'),
        ('requests', 'requests')
    ]

    for import_name, package_name in required_libraries:
        try:
            __import__(import_name)
            print(f"✓ {package_name} 已安装")
        except ImportError:
            print(f"✗ {package_name} 未安装")
            response = input(f"是否安装 {package_name}？(y/n): ").strip().lower()
            if response == 'y':
                try:
                    import subprocess
                    subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
                    print(f"✓ {package_name} 安装成功")
                except Exception as e:
                    print(f"✗ 安装 {package_name} 失败: {e}")
                    return False
            else:
                print(f"✗ 需要 {package_name} 库才能运行程序")
                return False
    return True


# Selenium相关导入
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.edge.options import Options
    from selenium.webdriver.edge.service import Service
    from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('grade_checker_enhanced.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ConfigManager:
    """配置管理类"""
    CONFIG_FILE = "config_enhanced.json"

    @classmethod
    def get_default_config(cls):
        return {
            "username": "",
            "password": "",
            "student_name": "",
            "headless": True,
            "timeout_seconds": 30,
            "last_query_time": "",
            "is_first_run": True,
            "last_academic_year": "2025-2026",
            "last_semester": "1",
            # 自动查询配置
            "auto_check_enabled": False,
            "auto_check_interval_minutes": 60,
            "last_auto_check_time": "",
            "last_grades_hash": "",
            # QQ邮箱推送配置
            "email_enabled": False,
            "email_sender": "",
            "email_auth_code": "",
            "email_receiver": "",
        }

    @classmethod
    def load_config(cls):
        default_config = cls.get_default_config()
        if os.path.exists(cls.CONFIG_FILE):
            try:
                with open(cls.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                for key in default_config:
                    if key not in config:
                        config[key] = default_config[key]
                return config
            except Exception as e:
                logger.error(f"加载配置文件失败: {e}")
                print(f"✗ 配置文件损坏，使用默认配置")
                return default_config
        else:
            return default_config

    @classmethod
    def save_config(cls, config):
        try:
            with open(cls.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            logger.info("配置已保存")
            return True
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            print(f"✗ 保存配置失败: {e}")
            return False


class EmailSender:
    """邮件发送器"""

    # 备用SMTP服务器配置
    SMTP_SERVERS = [
        {
            'name': 'QQ邮箱 (SSL)',
            'host': 'smtp.qq.com',
            'port': 465,
            'ssl': True
        },
        {
            'name': 'QQ邮箱 (TLS)',
            'host': 'smtp.qq.com',
            'port': 587,
            'ssl': False
        },
        {
            'name': 'QQ邮箱 (备用SSL)',
            'host': 'smtp.qq.com',
            'port': 465,
            'ssl': True,
            'timeout': 30
        }
    ]

    @classmethod
    def send_email(cls, sender, auth_code, receiver, title, content):
        """发送邮件，尝试多个SMTP服务器"""
        print("正在尝试发送邮件...")

        for server_config in cls.SMTP_SERVERS:
            server_name = server_config['name']
            host = server_config['host']
            port = server_config['port']
            use_ssl = server_config.get('ssl', False)
            timeout = server_config.get('timeout', 15)

            print(f"\n尝试使用 {server_name} (服务器: {host}:{port})...")

            try:
                # 创建邮件
                msg = MIMEMultipart()
                msg['From'] = formataddr(("成绩查询系统", sender))
                msg['To'] = formataddr(("用户", receiver))
                msg['Subject'] = title
                msg.attach(MIMEText(content, 'plain', 'utf-8'))

                if use_ssl:
                    # 使用SSL连接
                    context = ssl.create_default_context()
                    with smtplib.SMTP_SSL(host, port, context=context, timeout=timeout) as server:
                        server.login(sender, auth_code)
                        server.send_message(msg)
                else:
                    # 使用TLS连接
                    with smtplib.SMTP(host, port, timeout=timeout) as server:
                        server.starttls()
                        server.login(sender, auth_code)
                        server.send_message(msg)

                print(f"✓ 使用 {server_name} 发送成功！")
                return True

            except Exception as e:
                error_msg = str(e)
                print(f"✗ {server_name} 失败: {error_msg[:100]}...")
                continue

        return False


class MessageNotifier:
    """消息推送通知器"""

    def __init__(self, config):
        self.config = config
        self.email_enabled = config.get('email_enabled', False)

    def send_notification(self, title, content, grade_data=None):
        """发送通知"""
        success = True
        messages = []

        # 发送邮件通知
        if self.email_enabled:
            email_result = self.send_email(title, content, grade_data)
            if email_result:
                messages.append("✓ 邮件发送成功")
            else:
                messages.append("✗ 邮件发送失败")
                success = False

        return success, messages

    def send_email(self, title, content, grade_data=None):
        """发送邮件"""
        try:
            sender = self.config.get('email_sender', '')
            auth_code = self.config.get('email_auth_code', '')
            receiver = self.config.get('email_receiver', '')

            if not all([sender, auth_code, receiver]):
                print("✗ 邮箱配置不完整，无法发送邮件")
                return False

            # 格式化邮件内容
            email_content = self._format_email_content(content, grade_data)

            # 尝试发送邮件
            if EmailSender.send_email(sender, auth_code, receiver, title, email_content):
                logger.info(f"邮件发送成功: {sender} -> {receiver}")
                return True
            else:
                print("\n✗ 所有SMTP服务器尝试均失败")
                print("\n建议：")
                print("1. 检查网络连接是否正常")
                print("2. 确认QQ邮箱授权码是否正确")
                print("3. 检查防火墙是否阻止了SMTP连接")
                print("4. 尝试使用其他网络环境")
                return False

        except Exception as e:
            print(f"✗ 发送邮件时发生异常: {e}")
            logger.error(f"发送邮件失败: {e}")
            return False

    def _format_email_content(self, content, grade_data=None):
        """格式化邮件内容"""
        email_content = content

        if grade_data:
            grades = grade_data.get('grades', [])
            stats = grade_data.get('stats', {})
            academic_year = grade_data.get('academic_year', '')
            semester = grade_data.get('semester', '')
            student_name = grade_data.get('student_name', '')

            email_content += f"\n\n{'=' * 60}\n"
            email_content += f"湛江科技学院成绩查询结果\n"
            email_content += f"学生: {student_name}\n"
            email_content += f"学号: {self.config.get('username', '未知')}\n"
            email_content += f"学年: {academic_year}, 学期: {semester}\n"
            email_content += f"查询时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            email_content += f"{'=' * 60}\n"

            if grades:
                email_content += f"共查询到 {len(grades)} 门课程:\n"
                email_content += f"{'-' * 60}\n"

                for i, grade in enumerate(grades, 1):
                    course_name = grade.get('course_name', '未知课程')
                    score = grade.get('score', '未知')

                    if len(course_name) > 40:
                        course_name = course_name[:37] + "..."

                    email_content += f"{i:3d}. {course_name:<40} {score:>10}\n"

                email_content += f"{'-' * 60}\n"

                # 统计信息
                email_content += f"课程总数: {stats.get('course_count', 0)}\n"
                if stats.get('total_credits', 0) > 0:
                    email_content += f"总学分: {stats.get('total_credits', 0):.1f}\n"
                    email_content += f"平均学分绩点: {stats.get('gpa', 0):.2f}\n"
                    email_content += f"加权平均分: {stats.get('weighted_average', 0):.1f}\n"

        return email_content


class GradeCalculator:
    """成绩计算器"""

    @staticmethod
    def score_to_numeric(score_str):
        """将成绩转换为数值"""
        score_str = str(score_str).strip()
        score_map = {
            '优秀': 95.0,
            '良好': 85.0,
            '中等': 75.0,
            '及格': 65.0,
            '不及格': 0.0
        }
        if score_str in score_map:
            return score_map[score_str]
        try:
            return float(score_str)
        except ValueError:
            return 0.0

    @classmethod
    def calculate_stats(cls, grades):
        """计算统计信息"""
        total_grade_points = 0.0
        total_credits = 0.0
        weighted_score_sum = 0.0
        course_count = 0

        for grade in grades:
            credit = grade.get('credit', 0)
            if credit <= 0:
                continue

            grade_point = grade.get('grade_point', 0)
            score = grade.get('score', '')

            # 检查是否为补考/重考
            is_retake = False
            if isinstance(score, str):
                is_retake = '补考' in score or '重考' in score or '重修' in score

            if is_retake:
                grade_point = 0.0

            numeric_score = cls.score_to_numeric(score)
            total_grade_points += grade_point * credit
            total_credits += credit
            weighted_score_sum += numeric_score * credit
            course_count += 1

        if total_credits > 0:
            gpa = total_grade_points / total_credits
            weighted_average = weighted_score_sum / total_credits
        else:
            gpa = 0.0
            weighted_average = 0.0

        return {
            'gpa': round(gpa, 2),
            'weighted_average': round(weighted_average, 1),
            'total_credits': total_credits,
            'course_count': course_count,
            'total_grade_points': round(total_grade_points, 2)
        }

    @staticmethod
    def calculate_grades_hash(grades):
        """计算成绩的哈希值，用于检测成绩变化"""
        if not grades:
            return ""

        # 将成绩数据转换为字符串用于计算哈希
        grade_strings = []
        for grade in grades:
            grade_strings.append(f"{grade.get('course_name', '')}:{grade.get('score', '')}")

        grade_strings.sort()
        grades_text = "|".join(grade_strings)

        return hashlib.md5(grades_text.encode('utf-8')).hexdigest()


class GradeChecker:
    """成绩查询器"""

    def __init__(self, config):
        self.config = config
        self.driver = None
        self.timeout = config.get('timeout_seconds', 30)
        self.notifier = MessageNotifier(config)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
        })

    def run_query(self, is_auto_check=False):
        """执行查询"""
        try:
            if not is_auto_check:
                print("\n" + "=" * 60)
                print("开始查询成绩...")
            logger.info("开始查询成绩...")

            if not self._setup_driver():
                logger.error("初始化浏览器驱动失败")
                if not is_auto_check:
                    print("✗ 初始化浏览器驱动失败")
                return None

            login_result = self._login()
            if not login_result[0]:
                logger.error(f"登录失败: {login_result[1]}")
                if not is_auto_check:
                    print(f"✗ 登录失败 - {login_result[1]}")
                return None

            if not is_auto_check:
                print("✓ 登录成功")
            logger.info("登录成功")

            if not is_auto_check:
                print("正在查询成绩...")
            result = self._query_grades_new()
            if not result or not result['grades']:
                logger.error("未查询到成绩")
                if not is_auto_check:
                    print("⚠ 未查询到任何成绩")
                return None

            grades = result['grades']
            academic_year = result['academic_year']
            semester = result['semester']
            student_name = result.get('student_name', '')

            if student_name:
                self.config['student_name'] = student_name
                if not is_auto_check:
                    print(f"✓ 获取学生姓名: {student_name}")

            logger.info(f"查询完成，共找到{len(grades)}门课程成绩")
            logger.info(f"学年: {academic_year}, 学期: {semester}")

            stats = GradeCalculator.calculate_stats(grades)

            current_hash = GradeCalculator.calculate_grades_hash(grades)
            last_hash = self.config.get('last_grades_hash', '')

            grades_changed = current_hash != last_hash

            if is_auto_check and grades_changed and self.config.get('email_enabled', False):
                title = "成绩更新通知"
                content = f"检测到成绩有变化，请及时查看！\n学年: {academic_year}, 学期: {semester}"

                grade_data = {
                    'grades': grades,
                    'stats': stats,
                    'academic_year': academic_year,
                    'semester': semester,
                    'student_name': student_name
                }

                success, messages = self.notifier.send_notification(title, content, grade_data)
                if success:
                    print("✓ 成绩变化通知已发送")

                self.config['last_grades_hash'] = current_hash

            if not is_auto_check:
                self._display_grades(grades, stats, academic_year, semester)

            self.config['last_query_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.config['is_first_run'] = False
            self.config['last_academic_year'] = academic_year
            self.config['last_semester'] = semester

            if is_auto_check:
                self.config['last_auto_check_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            ConfigManager.save_config(self.config)

            return {
                'grades': grades,
                'stats': stats,
                'academic_year': academic_year,
                'semester': semester,
                'student_name': student_name,
                'grades_changed': grades_changed
            }

        except Exception as e:
            logger.error(f"查询过程中出错: {str(e)}")
            if not is_auto_check:
                print(f"✗ 查询过程中出错 - {str(e)}")
            return None
        finally:
            self.cleanup()

    def _setup_driver(self):
        """设置浏览器驱动"""
        if not SELENIUM_AVAILABLE:
            print("✗ selenium库未安装，无法运行浏览器")
            return False

        try:
            from selenium.webdriver.edge.service import Service as EdgeService
            from selenium.webdriver.edge.options import Options as EdgeOptions

            edge_options = EdgeOptions()
            edge_options.add_argument('--disable-gpu')
            edge_options.add_argument('--no-sandbox')
            edge_options.add_argument('--disable-dev-shm-usage')
            edge_options.add_argument('--disable-blink-features=AutomationControlled')
            edge_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            edge_options.add_experimental_option('useAutomationExtension', False)
            edge_options.add_argument('--lang=zh-CN')
            edge_options.add_argument(
                '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0'
            )
            edge_options.add_argument('--disable-extensions')
            edge_options.add_argument('--log-level=3')

            if self.config.get('headless', True):
                edge_options.add_argument('--headless=new')
            else:
                edge_options.add_argument('--start-maximized')

            try:
                self.driver = webdriver.Edge(options=edge_options)
            except Exception as e:
                possible_driver_paths = [
                    r"C:\Windows\System32\Microsoft\EdgeCore\108.0.1462.54\msedgedriver.exe",
                    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedgedriver.exe",
                    r"C:\Program Files\Microsoft\Edge\Application\msedgedriver.exe",
                    "msedgedriver.exe",
                    "driver/msedgedriver.exe",
                ]

                driver_found = False
                for driver_path in possible_driver_paths:
                    if os.path.exists(driver_path):
                        service = Service(executable_path=driver_path)
                        self.driver = webdriver.Edge(service=service, options=edge_options)
                        driver_found = True
                        break

                if not driver_found:
                    try:
                        service = EdgeService()
                        self.driver = webdriver.Edge(service=service, options=edge_options)
                    except Exception as e2:
                        return False

            self.driver.set_page_load_timeout(self.timeout)
            self.driver.set_script_timeout(self.timeout)

            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''\
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined
    });
    '''
            })

            return True

        except Exception as e:
            logger.error(f"初始化浏览器驱动失败: {e}")
            return False

    def _login(self):
        """登录教务系统"""
        try:
            login_url = "https://newjwxt.zjkju.edu.cn/xtgl/login_slogin.html"

            try:
                self.driver.get(login_url)
                time.sleep(2)
            except WebDriverException as e:
                if "net::ERR_CONNECTION_TIMED_OUT" in str(e):
                    return False, "网络连接超时"
                raise

            wait = WebDriverWait(self.driver, 10)

            try:
                username_input = wait.until(
                    EC.presence_of_element_located((By.ID, "yhm"))
                )
                username_input.clear()
                username_input.send_keys(self.config['username'])
            except:
                return False, "找不到用户名输入框"

            try:
                password_input = self.driver.find_element(By.ID, "mm")
                password_input.clear()
                password_input.send_keys(self.config['password'])
            except:
                return False, "找不到密码输入框"

            try:
                login_btn = self.driver.find_element(By.ID, "dl")
                login_btn.click()
            except:
                return False, "找不到登录按钮"

            time.sleep(3)

            current_url = self.driver.current_url
            if "login" in current_url or "slogin" in current_url:
                return False, "登录失败，请检查账号密码"

            student_name = self._extract_student_name_from_page()
            if student_name:
                self.config['student_name'] = student_name

            return True, "登录成功"

        except TimeoutException:
            return False, "登录超时，请检查网络连接"
        except Exception as e:
            logger.error(f"登录异常: {e}")
            return False, str(e)

    def _extract_student_name_from_page(self):
        """从页面中提取学生姓名"""
        try:
            time.sleep(2)

            name_selectors = [
                ".realname",
                ".username",
                "#realname",
                "#username",
                "span.navbar-brand",
                "span.user-name",
                "div.user-info span",
                "a.dropdown-toggle span",
            ]

            for selector in name_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        name = element.text.strip()
                        if (name and len(name) >= 2 and len(name) <= 10 and
                                '登录' not in name and '欢迎' not in name and
                                '系统' not in name and '管理' not in name and
                                not name.isdigit()):
                            return name
                except:
                    continue

            page_source = self.driver.page_source
            import re
            patterns = [
                r'姓名[：:]\s*([\u4e00-\u9fa5]{2,4})',
                r'xm[：:]\s*([\u4e00-\u9fa5]{2,4})',
                r'学生[：:]\s*([\u4e00-\u9fa5]{2,4})',
                r'欢迎你[，,]\s*([\u4e00-\u9fa5]{2,4})',
            ]

            for pattern in patterns:
                matches = re.findall(pattern, page_source)
                for match in matches:
                    if match and 2 <= len(match) <= 4:
                        return match

            return ""
        except Exception as e:
            return ""

    def _query_grades_new(self):
        """新的查询成绩方法"""
        try:
            grade_urls = [
                "https://newjwxt.zjkju.edu.cn/cjcx/cjcx_cxDgXscj.html?gnmkdm=N305005&layout=default",
                "https://newjwxt.zjkju.edu.cn/cjcx/cjcx_cxDgXscj.html",
                "https://newjwxt.zjkju.edu.cn/cjcx/cjcx_cxXsgrcj.html?doType=query"
            ]

            for grade_url in grade_urls:
                try:
                    self.driver.get(grade_url)
                    time.sleep(3)

                    if self._trigger_grade_query():
                        time.sleep(3)

                        result = self._try_ajax_query()
                        if result and result['grades']:
                            return result
                        else:
                            result = self._try_parse_html_table()
                            if result and result['grades']:
                                return result
                except Exception as e:
                    continue

            return {'grades': [], 'academic_year': "2025-2026", 'semester': "1", 'student_name': ''}

        except Exception as e:
            logger.error(f"查询成绩失败: {e}")
            return {'grades': [], 'academic_year': "2025-2026", 'semester': "1", 'student_name': ''}

    def _trigger_grade_query(self):
        """触发成绩查询"""
        try:
            try:
                query_btn = self.driver.find_element(By.XPATH, "//button[contains(text(), '查询')]")
                query_btn.click()
                return True
            except NoSuchElementException:
                pass

            try:
                query_btn = self.driver.find_element(By.ID, "cx")
                query_btn.click()
                return True
            except NoSuchElementException:
                pass

            try:
                self.driver.execute_script('''
                    var buttons = document.querySelectorAll('button, input[type="button"], input[type="submit"]');
                    for (var i = 0; i < buttons.length; i++) {
                        if (buttons[i].textContent.includes('查询') || 
                            buttons[i].value.includes('查询')) {
                            buttons[i].click();
                            return true;
                        }
                    }
                    return false;
                ''')
                return True
            except Exception as e:
                pass

            return False

        except Exception as e:
            return False

    def _try_ajax_query(self):
        """尝试使用AJAX查询成绩"""
        try:
            ajax_script = '''
                return new Promise((resolve, reject) => {
                    const xhr = new XMLHttpRequest();
                    xhr.open('POST', '/cjcx/cjcx_cxXsgrcj.html?doType=query&gnmkdm=N305005', true);
                    xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded;charset=UTF-8');
                    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
                    xhr.onload = function() {
                        if (xhr.status === 200) {
                            try {
                                const data = JSON.parse(xhr.responseText);
                                resolve(data);
                            } catch (e) {
                                reject('解析JSON失败: ' + e);
                            }
                        } else {
                            reject('请求失败，状态码: ' + xhr.status);
                        }
                    };
                    xhr.onerror = function() {
                        reject('网络错误');
                    };

                    const xnm = document.getElementById('xnm') ? document.getElementById('xnm').value : '2025';
                    const xqm = document.getElementById('xqm') ? document.getElementById('xqm').value : '3';

                    const params = new URLSearchParams({
                        'xnm': xnm,
                        'xqm': xqm,
                        'sfzgcj': '',
                        'kcbj': '',
                        '_search': 'false',
                        'nd': Date.now(),
                        'queryModel.showCount': 100,
                        'queryModel.currentPage': 1,
                        'queryModel.sortName': '',
                        'queryModel.sortOrder': 'asc',
                        'time': 0
                    });

                    xhr.send(params.toString());
                });
            '''

            json_data = self.driver.execute_script(ajax_script)
            time.sleep(2)

            if not json_data:
                return {'grades': [], 'academic_year': "2025-2026", 'semester': "1"}

            return self._parse_json_grades(json_data)

        except Exception as e:
            return {'grades': [], 'academic_year': "2025-2026", 'semester': "1"}

    def _parse_json_grades(self, json_data):
        """解析JSON格式的成绩数据"""
        try:
            grades = []

            if isinstance(json_data, dict) and 'items' in json_data:
                items = json_data['items']

                academic_year = "2025-2026"
                semester = "1"

                if items and len(items) > 0:
                    first_item = items[0]

                    if 'xnmmc' in first_item:
                        academic_year = str(first_item['xnmmc']).strip()
                    elif 'xnm' in first_item:
                        year = str(first_item['xnm'])
                        if len(year) == 4:
                            next_year = str(int(year) + 1)
                            academic_year = f"{year}-{next_year}"

                    if 'xqmmc' in first_item:
                        semester = str(first_item['xqmmc']).strip()
                    elif 'xqm' in first_item:
                        term = str(first_item['xqm'])
                        if term == '3':
                            semester = "1"
                        elif term == '12':
                            semester = "2"
                        else:
                            semester = term

                student_name = self._extract_student_name_from_json(json_data)

                for item in items:
                    course_name = item.get('kcmc', '').strip()
                    score = item.get('cj', '').strip()

                    if course_name and score:
                        try:
                            credit = float(item.get('xf', 0))
                        except:
                            credit = 0.0

                        try:
                            grade_point = float(item.get('jd', 0))
                        except:
                            grade_point = 0.0

                        grades.append({
                            'course_name': course_name,
                            'score': score,
                            'credit': credit,
                            'grade_point': grade_point,
                            'course_code': item.get('kch', ''),
                            'teacher': item.get('jsxm', ''),
                            'exam_type': item.get('khfsmc', '')
                        })

                return {
                    'grades': grades,
                    'academic_year': academic_year,
                    'semester': semester,
                    'student_name': student_name
                }

            return {'grades': [], 'academic_year': "2025-2026", 'semester': "1", 'student_name': ''}

        except Exception as e:
            return {'grades': [], 'academic_year': "2025-2026", 'semester': "1", 'student_name': ''}

    def _extract_student_name_from_json(self, json_data):
        """从JSON数据中提取学生姓名"""
        try:
            if isinstance(json_data, dict):
                if 'xm' in json_data:
                    student_name = str(json_data['xm']).strip()
                    if student_name and 2 <= len(student_name) <= 10:
                        return student_name

                if 'items' in json_data and isinstance(json_data['items'], list) and len(json_data['items']) > 0:
                    first_item = json_data['items'][0]

                    if 'xm' in first_item:
                        student_name = str(first_item['xm']).strip()
                        if student_name and 2 <= len(student_name) <= 10:
                            return student_name

                    possible_fields = ['xm', 'name', 'studentName', 'xsxm', 'userName', 'realName']
                    for field in possible_fields:
                        if field in first_item:
                            student_name = str(first_item[field]).strip()
                            if student_name and 2 <= len(student_name) <= 10:
                                return student_name

                possible_root_fields = ['xsxm', 'xm', 'name', 'studentName']
                for field in possible_root_fields:
                    if field in json_data:
                        student_name = str(json_data[field]).strip()
                        if student_name and 2 <= len(student_name) <= 10:
                            return student_name

            return self.config.get('student_name', '')

        except Exception as e:
            return self.config.get('student_name', '')

    def _try_parse_html_table(self):
        """尝试解析HTML表格"""
        try:
            time.sleep(3)

            table_selectors = [
                "#dataList",
                "table.table",
                "table.table-bordered",
                "table.datagrid-btable",
                "table.tab"
            ]

            table = None
            for selector in table_selectors:
                try:
                    table = self.driver.find_element(By.CSS_SELECTOR, selector)
                    break
                except:
                    continue

            if not table:
                return {'grades': [], 'academic_year': "2025-2026", 'semester': "1", 'student_name': ''}

            grades = []
            try:
                rows = table.find_elements(By.TAG_NAME, "tr")

                for i, row in enumerate(rows):
                    if i == 0:
                        continue

                    cols = row.find_elements(By.TAG_NAME, "td")
                    if len(cols) >= 4:
                        course_name = ""
                        score = ""
                        credit = 0.0

                        if len(cols) >= 6:
                            course_name = cols[2].text.strip() if cols[2].text.strip() else ""
                            score = cols[3].text.strip() if cols[3].text.strip() else ""

                            try:
                                credit_text = cols[4].text.strip()
                                credit = float(credit_text) if credit_text else 0.0
                            except:
                                credit = 0.0

                        if course_name and score and course_name != "课程名称" and score != "成绩":
                            grades.append({
                                'course_name': course_name,
                                'score': score,
                                'credit': credit,
                                'grade_point': 0.0
                            })

                academic_year = "2025-2026"
                semester = "1"

                try:
                    year_select = self.driver.find_element(By.ID, "xnm")
                    academic_year = year_select.get_attribute("value") or "2025"
                    if academic_year and len(academic_year) == 4:
                        next_year = str(int(academic_year) + 1)
                        academic_year = f"{academic_year}-{next_year}"
                except:
                    pass

                try:
                    term_select = self.driver.find_element(By.ID, "xqm")
                    semester_value = term_select.get_attribute("value") or "3"
                    if semester_value == '3':
                        semester = "1"
                    elif semester_value == '12':
                        semester = "2"
                    else:
                        semester = semester_value
                except:
                    pass

                student_name = self._extract_student_name_from_page()
                if not student_name:
                    student_name = self.config.get('student_name', '')

                return {
                    'grades': grades,
                    'academic_year': academic_year,
                    'semester': semester,
                    'student_name': student_name
                }

            except Exception as e:
                return {'grades': [], 'academic_year': "2025-2026", 'semester': "1", 'student_name': ''}

        except Exception as e:
            return {'grades': [], 'academic_year': "2025-2026", 'semester': "1", 'student_name': ''}

    def _display_grades(self, grades, stats, academic_year, semester):
        """显示成绩"""
        print("\n" + "=" * 80)
        print(f"湛江科技学院成绩查询结果")
        print(f"学生: {self.config.get('student_name', '未知')}")
        print(f"学号: {self.config.get('username', '未知')}")
        print(f"学年: {academic_year}, 学期: {semester}")
        print(f"查询时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 80)

        if not grades:
            print("未查询到任何成绩")
            return

        print(f"共查询到 {len(grades)} 门课程:")
        print("-" * 80)
        print("序号  课程名称".ljust(50) + "成绩")
        print("-" * 80)

        for i, grade in enumerate(grades, 1):
            course_name = grade.get('course_name', '未知课程')
            score = grade.get('score', '未知')

            course_display = course_name
            if len(course_display) > 45:
                course_display = course_display[:42] + "..."

            print(f"{i:3d}. {course_display:<45} {score:>10}")

        print("-" * 80)

        # 显示统计信息
        print(f"课程总数: {stats['course_count']}")
        if stats['total_credits'] > 0:
            print(f"总学分: {stats['total_credits']:.1f}")
            print(f"平均学分绩点: {stats['gpa']:.2f}")
            print(f"加权平均分: {stats['weighted_average']:.1f}")
        print("=" * 80 + "\n")

    def cleanup(self):
        """清理资源"""
        try:
            if self.driver:
                self.driver.quit()
        except Exception as e:
            pass


class AutoGradeChecker:
    """自动成绩查询器"""

    def __init__(self, config):
        self.config = config
        self.running = False
        self.thread = None

    def start(self):
        """开始自动查询"""
        if self.running:
            print("自动查询已在运行中")
            return

        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

        print("自动查询已启动")
        print(f"查询间隔: {self.config.get('auto_check_interval_minutes', 60)}分钟")
        print("程序将在后台运行，按Ctrl+C停止")

        self.config['auto_check_enabled'] = True
        ConfigManager.save_config(self.config)

    def stop(self):
        """停止自动查询"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

        print("自动查询已停止")

        self.config['auto_check_enabled'] = False
        ConfigManager.save_config(self.config)

    def _run_loop(self):
        """运行自动查询循环"""
        interval_minutes = self.config.get('auto_check_interval_minutes', 60)

        while self.running:
            try:
                print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始自动查询...")

                checker = GradeChecker(self.config)
                result = checker.run_query(is_auto_check=True)

                if result:
                    grades_count = len(result.get('grades', []))
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 自动查询完成，共找到{grades_count}门课程")

                    if result.get('grades_changed', False):
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检测到成绩变化")
                else:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 自动查询失败")

                for i in range(interval_minutes * 60):
                    if not self.running:
                        break
                    time.sleep(1)

            except Exception as e:
                logger.error(f"自动查询出错: {e}")
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 自动查询出错: {e}")

                for i in range(5 * 60):
                    if not self.running:
                        break
                    time.sleep(1)


def get_user_input():
    """获取用户输入"""
    print("\n" + "=" * 60)
    print("湛江科技学院成绩查询系统")
    print("=" * 60)

    config = ConfigManager.load_config()

    if config.get('is_first_run', True) or not config.get('username') or not config.get('password'):
        print("\n首次使用或配置不完整，请设置账号信息:")

        while True:
            username = input("学号: ").strip()
            if username:
                config['username'] = username
                break
            else:
                print("✗ 学号不能为空")

        while True:
            password = input("密码: ").strip()
            if password:
                config['password'] = password
                break
            else:
                print("✗ 密码不能为空")

        use_headless = input("\n是否使用无头模式？(y/n, 默认y): ").strip().lower()
        if use_headless == 'n':
            config['headless'] = False
            print("✓ 将显示浏览器窗口")
        else:
            config['headless'] = True
            print("✓ 使用无头模式")

        config['is_first_run'] = False
    else:
        print("\n使用已保存的配置:")
        print(f"学号: {config['username']}")
        print(f"学生姓名: {config.get('student_name', '未知')}")
        print(f"无头模式: {'是' if config.get('headless', True) else '否'}")

        use_saved = input("\n是否使用当前配置？(y/n, 默认y): ").strip().lower()
        if use_saved == 'n':
            print("\n重新输入账号信息:")

            while True:
                username = input("学号: ").strip()
                if username:
                    config['username'] = username
                    break
                else:
                    print("✗ 学号不能为空")

            while True:
                password = input("密码: ").strip()
                if password:
                    config['password'] = password
                    break
                else:
                    print("✗ 密码不能为空")

    # 配置推送通知
    print("\n" + "=" * 60)
    print("QQ邮箱推送配置（可选）")
    print("=" * 60)

    config_email = input("\n是否配置QQ邮箱推送？(y/n, 默认n): ").strip().lower()
    if config_email == 'y':
        config['email_enabled'] = True

        while True:
            email_sender = input("发件人QQ邮箱: ").strip()
            if email_sender and '@qq.com' in email_sender:
                config['email_sender'] = email_sender
                break
            else:
                print("✗ 请输入有效的QQ邮箱")

        print("\n注意：QQ邮箱授权码获取方法：")
        print("1. 登录QQ邮箱")
        print("2. 点击【设置】->【账户】")
        print("3. 找到【POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV服务】")
        print("4. 开启【POP3/SMTP服务】")
        print("5. 按照提示发送短信后，点击【我已发送】")
        print("6. 复制生成的授权码（16位）\n")

        while True:
            email_auth_code = input("QQ邮箱授权码: ").strip()
            if email_auth_code:
                config['email_auth_code'] = email_auth_code
                break
            else:
                print("✗ 授权码不能为空")

        while True:
            email_receiver = input("收件人邮箱（可填自己）: ").strip()
            if email_receiver and '@' in email_receiver:
                config['email_receiver'] = email_receiver
                break
            else:
                print("✗ 请输入有效的邮箱地址")

        print("✓ QQ邮箱推送已配置")
    else:
        config['email_enabled'] = False

    # 配置自动查询
    print("\n" + "=" * 60)
    print("自动查询配置（可选）")
    print("=" * 60)

    config_auto = input("\n是否启用自动查询？(y/n, 默认n): ").strip().lower()
    if config_auto == 'y':
        config['auto_check_enabled'] = True

        while True:
            try:
                interval = input("自动查询间隔（分钟，默认60）: ").strip()
                if interval:
                    interval_minutes = int(interval)
                    if interval_minutes >= 5:
                        config['auto_check_interval_minutes'] = interval_minutes
                        break
                    else:
                        print("✗ 间隔时间不能小于5分钟")
                else:
                    config['auto_check_interval_minutes'] = 60
                    break
            except ValueError:
                print("✗ 请输入有效的数字")

        print(f"✓ 自动查询已启用，间隔{config['auto_check_interval_minutes']}分钟")
    else:
        config['auto_check_enabled'] = False

    try:
        timeout = input("\n超时时间(秒，默认30): ").strip()
        if timeout:
            config['timeout_seconds'] = int(timeout)
            print(f"✓ 超时时间设置为: {timeout}秒")
        else:
            config['timeout_seconds'] = 30
            print("✓ 使用默认超时时间: 30秒")
    except ValueError:
        print("✗ 输入无效，使用默认超时时间: 30秒")
        config['timeout_seconds'] = 30

    print("\n" + "=" * 60)
    print("配置完成!")
    print("=" * 60)

    return config


def main():
    """主函数"""
    try:
        print("正在启动程序...")

        if not check_and_install_dependencies():
            print("✗ 依赖库检查失败，程序退出")
            input("按回车键退出...")
            return

        if not SELENIUM_AVAILABLE:
            print("✗ selenium库未安装，程序无法运行")
            input("按回车键退出...")
            return

        config = get_user_input()

        print("\n正在保存配置...")
        ConfigManager.save_config(config)

        print("正在初始化查询器...")
        checker = GradeChecker(config)

        auto_checker = AutoGradeChecker(config)

        print("\n" + "=" * 60)
        print("请选择运行模式:")
        print("1. 单次查询")
        print("2. 启动自动查询（后台运行）")
        print("3. 退出程序")

        choice = input("\n请选择 (1-3, 默认1): ").strip()

        if choice == '2':
            auto_checker.start()

            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n接收到中断信号，正在停止...")
                auto_checker.stop()

        elif choice == '3':
            print("程序退出")
            return
        else:
            print("\n" + "=" * 60)
            print("开始查询成绩...")
            result = checker.run_query()

            if result:
                print("\n" + "=" * 60)
                print("查询完成!")
                print("=" * 60)

                if config.get('email_enabled', False):
                    send_notice = input("\n是否发送成绩通知？(y/n, 默认n): ").strip().lower()
                    if send_notice == 'y':
                        title = "湛江科技学院成绩查询结果"
                        content = f"成绩查询已完成，共查询到{len(result['grades'])}门课程。\n"
                        content += f"学生：{result['student_name']}\n"
                        content += f"学号：{config['username']}\n"
                        content += f"学年：{result['academic_year']}，学期：{result['semester']}\n"
                        content += f"查询时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

                        grade_data = {
                            'grades': result['grades'],
                            'stats': result['stats'],
                            'academic_year': result['academic_year'],
                            'semester': result['semester'],
                            'student_name': result['student_name']
                        }

                        success, messages = checker.notifier.send_notification(title, content, grade_data)
                        for msg in messages:
                            print(msg)
            else:
                print("\n" + "=" * 60)
                print("查询失败!")
                print("=" * 60)

        print(f"\n详细日志请查看: grade_checker_enhanced.log")
        print("如需重新查询，请再次运行本程序。")

    except KeyboardInterrupt:
        print("\n\n✗ 程序被用户中断")
    except Exception as e:
        print(f"\n✗ 程序运行出错: {e}")
        import traceback
        traceback.print_exc()

    input("\n按回车键退出...")


if __name__ == "__main__":
    main()