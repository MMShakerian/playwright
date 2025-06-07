import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright, TimeoutError, Error
from collections import deque
import time
import requests
import threading
import queue
import json
import os
import datetime
import subprocess
import re  # Added import for regular expressions

class WebsiteTesterApp:
    """
    کلاس اصلی برنامه آزمون وب‌سایت‌ها با Tkinter و Playwright
    """
    def __init__(self, master):
        """
        راه‌اندازی اولیه برنامه
        :param master: پنجره اصلی Tkinter
        """
        self.master = master
        self.master.title("Website Test Tool - Alpha")
        self.master.resizable(False, False)
        
        # تنظیم اندازه و موقعیت پنجره
        self.window_width = 800
        self.window_height = 600
        screen_width = self.master.winfo_screenwidth()
        screen_height = self.master.winfo_screenheight()
        x_position = (screen_width - self.window_width) // 2
        y_position = (screen_height - self.window_height) // 2
        self.master.geometry(f"{self.window_width}x{self.window_height}+{x_position}+{y_position}")
        
        # متغیرهای مربوط به Playwright و مرورگر
        self.playwright = None
        self.browser = None
        self.browser_context = None
        
        # وضعیت برنامه
        self._crawling_in_progress = False
        self.has_crawl_data = False
        self.crawled_pages_data = {}
        self.start_url = ""
        
        # متغیرهای گزارش لینک‌ها
        self.all_broken_links = []           
        self.all_external_links_info = []    
        
        # متغیرهای جدید برای threading
        self.ui_queue = queue.Queue()
        self.crawl_thread = None
        
        # متغیر برای سناریوی فعلی
        self.current_scenario = None
        
        # دایرکتوری پیش‌فرض برای ذخیره خودکار گزارش‌ها
        self.default_auto_save_dir = os.path.join(os.path.expanduser("~"), "WebsiteTesterApp_Reports")
        # ایجاد دایرکتوری پیش‌فرض اگر وجود نداشته باشد
        try:
            os.makedirs(self.default_auto_save_dir, exist_ok=True)
        except Exception as e:
            print(f"خطا در ایجاد دایرکتوری پیش‌فرض ذخیره‌سازی: {e}")
        
        # ایجاد ابزارک‌های رابط کاربری
        self._create_widgets()
        
        # اطمینان از بستن مرورگر در زمان خروج
        self.master.protocol("WM_DELETE_WINDOW", self._on_closing)

        # شروع پردازش پیام‌های UI
        self._process_ui_queue()
    
    def _create_widgets(self):
        """
        ایجاد و چیدمان تمام ابزارک‌های رابط کاربری
        """
        # فریم بالایی برای ورود آدرس و دکمه‌ها
        self.top_frame = tk.Frame(self.master)
        self.top_frame.pack(fill='x', padx=10, pady=5)
        
        # بخش ورود آدرس سایت
        self.url_label = tk.Label(self.top_frame, text="Enter Website URL:", font=("Arial", 10))
        self.url_label.pack(side='left', pady=5)
        
        self.url_entry = tk.Entry(self.top_frame, width=50, font=("Arial", 10))
        self.url_entry.pack(side='left', padx=5, pady=5, expand=True, fill='x')
        
        # افزودن فیلد تنظیم حداکثر عمق خزش
        self.max_depth_label = tk.Label(self.top_frame, text="Max Crawl Depth:", font=("Arial", 10))
        self.max_depth_label.pack(side='left', pady=5)
        
        self.max_depth_entry = tk.Entry(self.top_frame, width=5, font=("Arial", 10))
        self.max_depth_entry.insert(0, "1")  # مقدار پیش‌فرض
        self.max_depth_entry.pack(side='left', padx=(0, 5), pady=5)
        
        # دکمه شروع آزمون
        self.start_button = tk.Button(
            self.top_frame, 
            text="Start Test", 
            font=("Arial", 10),
            command=self._handle_start_test
        )
        self.start_button.pack(side='left', pady=5, padx=5)
        
        # دکمه ذخیره گزارش‌ها
        self.save_reports_button = tk.Button(
            self.top_frame,
            text="Save Reports",
            font=("Arial", 10),
            command=self._handle_save_reports,
            state=tk.DISABLED  # در ابتدا غیرفعال است
        )
        self.save_reports_button.pack(side='left', pady=5, padx=5)
        
        # فریم دوم برای ورود فایل سناریو و ضبط سناریو
        self.scenario_frame = tk.Frame(self.master)
        self.scenario_frame.pack(fill='x', padx=10, pady=0)
        
        # برچسب فایل سناریو
        self.scenario_label = tk.Label(self.scenario_frame, text="Scenario File (JSON):", font=("Arial", 10))
        self.scenario_label.pack(side='left', pady=5)
        
        # ورودی مسیر فایل سناریو
        self.scenario_file_entry = tk.Entry(self.scenario_frame, width=50, font=("Arial", 10))
        self.scenario_file_entry.pack(side='left', padx=5, pady=5, expand=True, fill='x')
        
        # دکمه مرور برای انتخاب فایل سناریو
        self.browse_scenario_button = tk.Button(
            self.scenario_frame,
            text="Browse...",
            font=("Arial", 10),
            command=self._browse_for_scenario_file
        )
        self.browse_scenario_button.pack(side='left', pady=5, padx=5)
        
        # دکمه ضبط سناریو
        self.record_scenario_button = tk.Button(
            self.scenario_frame,
            text="Record Scenario",
            font=("Arial", 10),
            command=self._handle_record_scenario
        )
        self.record_scenario_button.pack(side='left', pady=5, padx=5)
        
        # دکمه جدید تبدیل اسکریپت به JSON
        self.convert_script_button = tk.Button(
            self.scenario_frame,
            text="Convert Script...",
            font=("Arial", 10),
            command=self._handle_convert_script_to_json
        )
        self.convert_script_button.pack(side='left', pady=5, padx=5)
        
        # فریم برای notebook با سه تب (لاگ، درختی، گزارش لینک)
        self.notebook = ttk.Notebook(self.master)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=5)
        
        # ایجاد تب‌ها
        self.log_frame = ttk.Frame(self.notebook)
        self.result_frame = ttk.Frame(self.notebook)
        self.link_report_frame = ttk.Frame(self.notebook)
        
        self.notebook.add(self.log_frame, text="Log")
        self.notebook.add(self.result_frame, text="Tree View")
        self.notebook.add(self.link_report_frame, text="Link Report")
        
        # ذخیره اندیس تب گزارش لینک
        self.link_report_tab_index = 2
        
        # ناحیه نمایش خروجی متنی (لاگ)
        self.output_text_area = tk.Text(self.log_frame, font=("Arial", 10))
        self.output_text_area.pack(expand=True, fill='both', padx=5, pady=5)
        
        # اضافه کردن اسکرول‌بار برای متن
        self.text_scrollbar = ttk.Scrollbar(self.log_frame, command=self.output_text_area.yview)
        self.text_scrollbar.pack(side='right', fill='y')
        self.output_text_area.config(yscrollcommand=self.text_scrollbar.set)
        
        # درخت نتایج
        self.tree = None
        
        # ناحیه گزارش لینک
        self.link_report_area = tk.Text(self.link_report_frame, font=("Arial", 10))
        self.link_report_area.pack(expand=True, fill='both', padx=5, pady=5)
        self.link_report_scrollbar = ttk.Scrollbar(self.link_report_frame,
                                                   command=self.link_report_area.yview)
        self.link_report_scrollbar.pack(side='right', fill='y')
        self.link_report_area.config(yscrollcommand=self.link_report_scrollbar.set)
    
    def _handle_convert_script_to_json(self):
        """
        مدیریت تبدیل اسکریپت پایتون تولید شده توسط codegen به فرمت JSON سناریو
        """
        # درخواست فایل اسکریپت پایتون ورودی
        input_py_path = filedialog.askopenfilename(
            title="انتخاب فایل اسکریپت پایتون از codegen",
            filetypes=(("Python files", "*.py"), ("All files", "*.*"))
        )
        
        # اگر کاربر فایلی انتخاب نکرده باشد، خروج
        if not input_py_path:
            return
            
        # درخواست مسیر ذخیره‌سازی فایل JSON
        output_json_path = filedialog.asksaveasfilename(
            title="ذخیره فایل سناریو JSON",
            defaultextension=".json",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*"))
        )
        
        # اگر کاربر مسیر ذخیره‌سازی را انتخاب نکرده باشد، خروج
        if not output_json_path:
            return
            
        # تلاش برای تجزیه و تحلیل اسکریپت و تبدیل آن به فرمت JSON
        try:
            # لاگ شروع تبدیل
            self.output_text_area.insert(tk.END, f"شروع تبدیل اسکریپت {os.path.basename(input_py_path)} به فرمت JSON...\n")
            self.output_text_area.see(tk.END)
            self.output_text_area.update_idletasks()
            
            # فراخوانی متد تجزیه اسکریپت
            actions, target_url = self._parse_codegen_script(input_py_path)
            
            # بررسی اینکه آیا تجزیه موفقیت‌آمیز بوده است
            if not actions:
                raise ValueError("هیچ اقدامی از اسکریپت استخراج نشد. لطفاً اسکریپت را بررسی کنید.")
                
            # ساخت ساختار کامل سناریو JSON
            script_name = os.path.basename(input_py_path).replace('.py', '')
            scenario_data = {
                "name": f"Scenario_{script_name}",
                "target_url_pattern": target_url,
                "actions": actions
            }
            
            # ذخیره داده‌های JSON در فایل خروجی
            with open(output_json_path, 'w', encoding='utf-8') as json_file:
                json.dump(scenario_data, json_file, ensure_ascii=False, indent=2)
                
            # نمایش پیام موفقیت
            success_msg = f"تبدیل با موفقیت انجام شد. {len(actions)} اقدام استخراج شد.\nفایل JSON در مسیر زیر ذخیره شد:\n{output_json_path}\n\n"
            messagebox.showinfo("تبدیل موفقیت‌آمیز", success_msg)
            
            # افزودن به لاگ
            self.output_text_area.insert(tk.END, success_msg)
            self.output_text_area.see(tk.END)
            
            # قرار دادن مسیر فایل JSON در فیلد ورودی سناریو
            self.scenario_file_entry.delete(0, tk.END)
            self.scenario_file_entry.insert(0, output_json_path)
            
        except Exception as e:
            # نمایش پیام خطا
            error_msg = f"خطا در تبدیل اسکریپت: {str(e)}"
            messagebox.showerror("خطا در تبدیل", error_msg)
            
            # افزودن به لاگ
            self.output_text_area.insert(tk.END, error_msg + "\n\n")
            self.output_text_area.see(tk.END)
    
    def _parse_codegen_script(self, python_script_path):
        """
        تجزیه و تحلیل اسکریپت پایتون تولید شده توسط codegen و استخراج اقدامات
        
        :param python_script_path: مسیر فایل اسکریپت پایتون
        :return: tuple شامل (لیست اقدامات استخراج شده، URL هدف)
        """
        # خواندن محتوای فایل اسکریپت
        try:
            with open(python_script_path, 'r', encoding='utf-8') as script_file:
                script_content = script_file.read()
        except Exception as e:
            raise ValueError(f"خطا در خواندن فایل اسکریپت: {str(e)}")
            
        # لیست برای ذخیره اقدامات استخراج شده
        actions = []
        
        # متغیر برای ذخیره URL هدف (از اولین page.goto)
        target_url = None
        
        # خواندن محتوا به خطوط برای تشخیص کلیک‌های تکراری
        script_lines = script_content.splitlines()
        
        # الگوهای regex برای تطبیق با دستورات مختلف Playwright
        
        # الگوی page.goto - پشتیبانی از هر دو نوع کوتیشن
        goto_pattern = re.compile(r'page\.goto\(["\']([^"\']+)["\']\s*(?:,\s*{[^}]*})?\)')
        goto_matches = goto_pattern.findall(script_content)
        if goto_matches:
            target_url = goto_matches[0]  # اولین URL پیدا شده به عنوان URL هدف
        
        # لیست برای نگهداری اقدامات کلیک (برای فیلتر کردن کلیک‌های تکراری)
        click_actions = []
        
        # تجزیه و تحلیل خط به خط
        i = 0
        while i < len(script_lines):
            line = script_lines[i].strip()
            
            # بررسی خط کلیک
            if '.click()' in line:
                # تطبیق الگوی با page.locator().click()
                locator_match = re.search(r'page\.locator\(["\']([^"\']+)["\'](?:\s*,\s*{[^}]*})?\)\.click\((?:[^)]*)\)', line)
                
                if locator_match:
                    selector = locator_match.group(1)
                    skip_click = False
                    
                    # بررسی خط بعدی برای fill روی همان المنت
                    if i + 1 < len(script_lines):
                        next_line = script_lines[i + 1].strip()
                        if '.fill(' in next_line:
                            next_locator_match = re.search(r'page\.locator\(["\']([^"\']+)["\'](?:\s*,\s*{[^}]*})?\)\.fill\(', next_line)
                            if next_locator_match and next_locator_match.group(1) == selector:
                                        skip_click = True
                    
                    if not skip_click:
                        actions.append({
                            "type": "CLICK_ELEMENT",
                            "selector": selector
                        })
                    
                # تطبیق الگوی با page.get_by_xxx().click()
                getby_match = re.search(r'page\.(get_by_\w+\([^)]*\))\.click\((?:[^)]*)\)', line)
                if getby_match:
                    selector_method = getby_match.group(1)
                    skip_click = False
                    
                    # بررسی خط بعدی برای fill روی همان المنت
                    if i + 1 < len(script_lines):
                        next_line = script_lines[i + 1].strip()
                        if '.fill(' in next_line:
                            next_getby_match = re.search(r'page\.(get_by_\w+\([^)]*\))\.fill\(', next_line)
                            if next_getby_match and next_getby_match.group(1) == selector_method:
                                skip_click = True
                    
                    if not skip_click:
                        actions.append({
                            "type": "CLICK_ELEMENT",
                            "selector": selector_method
                        })
            
            # بررسی خط check (چک باکس)
            elif '.check()' in line:
                # تطبیق الگوی با page.locator().check()
                locator_check_match = re.search(r'page\.locator\(["\']([^"\']+)["\'](?:\s*,\s*{[^}]*})?\)\.check\((?:[^)]*)\)', line)
                
                if locator_check_match:
                    selector = locator_check_match.group(1)
                    actions.append({
                        "type": "CHECK_ELEMENT",
                        "selector": selector
                    })
                
                # تطبیق الگوی با page.get_by_xxx().check()
                getby_check_match = re.search(r'page\.(get_by_\w+\([^)]*\))\.check\((?:[^)]*)\)', line)
                if getby_check_match:
                    selector_method = getby_check_match.group(1)
                    actions.append({
                        "type": "CHECK_ELEMENT",
                        "selector": selector_method
                    })
            
            # تطبیق با page.fill (با استفاده از page.locator و سایر روش‌ها)
            elif '.fill(' in line:
                # الگو برای page.locator().fill()
                locator_fill_match = re.search(r'page\.locator\(["\']([^"\']+)["\']\)\.fill\(["\']([^"\']*)["\'](?:\s*,\s*{[^}]*})?\)', line)
                if locator_fill_match:
                    selector = locator_fill_match.group(1)
                    text = locator_fill_match.group(2)
                    actions.append({
                        "type": "FILL_INPUT",
                        "selector": selector,
                        "text": text
                    })
                
                # الگو برای page.get_by_xxx().fill()
                getby_fill_match = re.search(r'page\.(get_by_\w+\([^)]*\))\.fill\(["\']([^"\']*)["\'](?:\s*,\s*{[^}]*})?\)', line)
                if getby_fill_match:
                    selector_method = getby_fill_match.group(1)
                    text = getby_fill_match.group(2)
                    actions.append({
                        "type": "FILL_INPUT",
                        "selector": selector_method,
                        "text": text
                    })
            
            # تطبیق با page.wait_for_navigation و page.wait_for_load_state
            elif 'page.wait_for_navigation' in line:
                # الگو برای page.wait_for_navigation با یا بدون timeout
                wait_nav_match = re.search(r'page\.wait_for_navigation\((?:{.*?timeout["\']?\s*:\s*(\d+).*?}|.*?)\)', line)
                if wait_nav_match:
                    timeout_match = wait_nav_match.group(1)
                    timeout = int(timeout_match) if timeout_match else 30000  # مقدار پیش‌فرض 30 ثانیه
                    actions.append({
                        "type": "WAIT_FOR_NAVIGATION",
                        "timeout": timeout
                    })
                    
            elif 'page.wait_for_load_state' in line:
                # الگو برای page.wait_for_load_state با یا بدون timeout
                wait_load_match = re.search(r'page\.wait_for_load_state\(["\']?(\w+)?["\']?(?:.*?timeout["\']?\s*:\s*(\d+).*?)?\)', line)
                if wait_load_match:
                    state = wait_load_match.group(1)
                    timeout_match = wait_load_match.group(2)
                    timeout = int(timeout_match) if timeout_match else 30000  # مقدار پیش‌فرض 30 ثانیه
                    actions.append({
                        "type": "WAIT_FOR_NAVIGATION",
                        "timeout": timeout,
                        "state": state if state else "load"
                    })
            
            i += 1
            
        # اگر URL هدف پیدا نشد، از نام فایل به عنوان جایگزین استفاده می‌کنیم
        if not target_url:
            target_url = os.path.basename(python_script_path).replace('.py', '')
            
        # اضافه کردن پیام لاگ با جزئیات اقدامات استخراج شده
        action_types_count = {}
        for action in actions:
            action_type = action['type']
            action_types_count[action_type] = action_types_count.get(action_type, 0) + 1
            
        log_msg = f"تجزیه اسکریپت کامل شد. استخراج {len(actions)} اقدام:\n"
        for action_type, count in action_types_count.items():
            log_msg += f"  • {action_type}: {count} مورد\n"
            
        self.output_text_area.insert(tk.END, log_msg)
        self.output_text_area.see(tk.END)
        
        return actions, target_url

    def _handle_record_scenario(self):
        """
        مدیریت دکمه ضبط سناریو - راه‌اندازی ابزار codegen پلی‌رایت
        """
        # درخواست URL شروع برای ضبط سناریو
        start_url = simpledialog.askstring(
            "ضبط سناریو", 
            "لطفاً آدرس URL شروع برای ضبط سناریو را وارد کنید:", 
            parent=self.master
        )
        
        # بررسی اینکه URL وارد شده باشد
        if not start_url:
            return
            
        # اضافه کردن پروتکل پیش‌فرض اگر لازم باشد
        if not start_url.startswith(('http://', 'https://')):
            start_url = 'https://' + start_url
            
        # تعیین مسیر فایل خروجی برای اقدامات ضبط شده
        output_dir = self.default_auto_save_dir
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        record_filename = f"recorded_actions_{timestamp}.py"
        output_path = os.path.join(output_dir, record_filename)
        
        # اطمینان از وجود دایرکتوری خروجی
        try:
            os.makedirs(output_dir, exist_ok=True)
        except Exception as e:
            messagebox.showerror("خطا", f"خطا در ایجاد دایرکتوری خروجی: {str(e)}")
            return
            
        # اطلاع‌رسانی به کاربر در مورد شروع ضبط
        messagebox.showinfo(
            "ضبط سناریو شروع شد", 
            "ضبط سناریو شروع شده است. لطفاً با پنجره مرورگر جدید کار کنید.\n"
            "پس از اتمام، پنجره Playwright Inspector را ببندید."
        )
        
        # تلاش برای اجرای دستور codegen پلی‌رایت
        try:
            # ایجاد و اجرای دستور codegen
            command = [
                r"C:\Users\mohmmad moein\AppData\Roaming\npm\playwright.cmd",
                "codegen",
                start_url,
                "-o", output_path,
                "--target", "python", # <--- تغییر در اینجا
                "-b", "chromium"
            ]
            
            # اضافه کردن پیام به ناحیه لاگ
            self.output_text_area.insert(tk.END, f"شروع ضبط سناریو برای {start_url}...\n")
            self.output_text_area.see(tk.END)
            self.output_text_area.update_idletasks()
            
            # اجرای codegen به عنوان یک فرآیند فرعی
            process = subprocess.run(command, check=True)
            
            # اطلاع‌رسانی به کاربر پس از اتمام ضبط
            messagebox.showinfo(
                "ضبط سناریو تمام شد", 
                f"ضبط سناریو با موفقیت به پایان رسید.\n"
                f"اقدامات در فایل زیر ذخیره شدند:\n{output_path}\n\n"
                f"می‌توانید از دکمه \"Convert Script...\" برای تبدیل این فایل به سناریو JSON استفاده کنید."
            )
            
            # اضافه کردن پیام به ناحیه لاگ
            self.output_text_area.insert(tk.END, f"ضبط سناریو با موفقیت به پایان رسید. اقدامات در {output_path} ذخیره شدند.\n\n")
            self.output_text_area.see(tk.END)
            self.output_text_area.update_idletasks()
            
        except FileNotFoundError:
            # خطا اگر دستور playwright پیدا نشود
            error_msg = (
                "دستور 'playwright' یافت نشد. لطفاً مطمئن شوید که پلی‌رایت نصب شده است.\n"
                "برای نصب پلی‌رایت: 'pip install playwright' و سپس 'playwright install'\n"
            )
            messagebox.showerror("خطا", error_msg)
            self.output_text_area.insert(tk.END, error_msg + "\n")
            self.output_text_area.see(tk.END)
            
        except subprocess.CalledProcessError as e:
            # خطا اگر اجرای codegen با خطا مواجه شود
            error_msg = f"خطا در اجرای ضبط سناریو: {str(e)}"
            messagebox.showerror("خطا", error_msg)
            self.output_text_area.insert(tk.END, error_msg + "\n")
            self.output_text_area.see(tk.END)
            
        except Exception as e:
            # سایر خطاها
            error_msg = f"خطای غیرمنتظره: {str(e)}"
            messagebox.showerror("خطا", error_msg)
            self.output_text_area.insert(tk.END, error_msg + "\n")
            self.output_text_area.see(tk.END)

    def _browse_for_scenario_file(self):
        """
        باز کردن پنجره انتخاب فایل برای انتخاب فایل سناریو JSON
        """
        file_path = filedialog.askopenfilename(
            title="انتخاب فایل سناریو JSON",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*"))
        )
        if file_path:  # اگر کاربر فایلی انتخاب کرده باشد
            self.scenario_file_entry.delete(0, tk.END)  # پاک کردن متن فعلی
            self.scenario_file_entry.insert(0, file_path)  # اضافه کردن مسیر جدید
    
    def _load_scenario(self, file_path):
        """
        بارگذاری و اعتبارسنجی فایل سناریو JSON
        
        :param file_path: مسیر فایل سناریو JSON
        :return: دیکشنری حاوی اطلاعات سناریو یا None در صورت خطا
        """
        try:
            # بررسی وجود فایل
            if not os.path.exists(file_path):
                self.output_text_area.insert(tk.END, f"خطا: فایل سناریو '{file_path}' یافت نشد.\n")
                return None
                
            # باز کردن و خواندن فایل JSON
            with open(file_path, 'r', encoding='utf-8') as file:
                scenario_data = json.load(file)
                
            # اعتبارسنجی ساختار پایه
            required_keys = ["name", "target_url_pattern", "actions"]
            for key in required_keys:
                if key not in scenario_data:
                    self.output_text_area.insert(tk.END, f"خطا: کلید '{key}' در فایل سناریو یافت نشد.\n")
                    return None
                    
            # اعتبارسنجی نوع داده‌ها
            if not isinstance(scenario_data["name"], str):
                self.output_text_area.insert(tk.END, "خطا: فیلد 'name' باید یک رشته باشد.\n")
                return None
                
            if not isinstance(scenario_data["target_url_pattern"], str):
                self.output_text_area.insert(tk.END, "خطا: فیلد 'target_url_pattern' باید یک رشته باشد.\n")
                return None
                
            if not isinstance(scenario_data["actions"], list):
                self.output_text_area.insert(tk.END, "خطا: فیلد 'actions' باید یک لیست باشد.\n")
                return None
                
            # سناریو معتبر است
            return scenario_data
            
        except json.JSONDecodeError as e:
            self.output_text_area.insert(tk.END, f"خطا در تجزیه فایل JSON: {str(e)}\n")
            return None
            
        except Exception as e:
            self.output_text_area.insert(tk.END, f"خطا در بارگذاری فایل سناریو: {str(e)}\n")
            return None
    
    def _on_closing(self):
        """
        مدیریت رویداد بستن پنجره - اطمینان از بستن مرورگر و thread ها
        """
        # متوقف کردن crawling thread اگر در حال اجرا است
        if self.crawl_thread and self.crawl_thread.is_alive():
            # نمی‌توانیم thread را مجبور به توقف کنیم، اما مرورگر را می‌بندیم
            self._close_browser()
            # صبر کوتاهی برای اتمام thread
            try:
                self.crawl_thread.join(timeout=2)
            except:
                pass
        
        self._close_browser()
        self.master.destroy()
    
    def _close_browser(self):
        """
        بستن مرورگر و آزادسازی منابع آن به درستی
        """
        try:
            if self.browser:
                self.browser.close()
                self.browser = None
            
            if self.playwright:
                self.playwright.stop()  # استفاده صحیح از stop() به جای del
                self.playwright = None
                
            self.browser_context = None
            
        except Exception as e:
            print(f"Error closing browser: {str(e)}")
    
    def _init_browser(self):
        """
        راه‌اندازی مرورگر Playwright به درستی
        """
        if self.browser and self.playwright and self.browser_context:
            return True
            
        try:
            # راه‌اندازی نمونه Playwright 
            if not self.playwright:
                self.playwright = sync_playwright().start()
            
            # راه‌اندازی مرورگر
            if not self.browser:
                self.browser = self.playwright.chromium.launch(
                    headless=False,
                    args=['--disable-web-security', '--no-sandbox', '--disable-features=IsolateOrigins,site-per-process']
                )
            
            # ایجاد زمینه مرورگر
            if not self.browser_context:
                self.browser_context = self.browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    viewport={'width': 1280, 'height': 800}
                )
                # تنظیم زمان انتظار پیش‌فرض
                self.browser_context.set_default_timeout(60000)  # 60 seconds
                
            return True
            
        except Exception as e:
            self.output_text_area.insert(tk.END, f"Error initializing browser: {str(e)}\n")
            self._close_browser()  # اطمینان از پاکسازی منابع در صورت خطا
            return False
    
    def _handle_start_test(self):
        """
        پردازش دکمه شروع آزمون و اجرای خزش وب روی آدرس وارد شده
        """
        # جلوگیری از شروع چندین عملیات خزش همزمان
        if self._crawling_in_progress:
            self._clear_output()
            self.output_text_area.insert(tk.END, "A crawl is already in progress. Please wait for it to finish.")
            return
        
        # دریافت آدرس از فیلد ورودی
        url = self.url_entry.get().strip()
        
        # بررسی خالی نبودن فیلد آدرس
        if not url:
            self._clear_output()
            self.output_text_area.insert(tk.END, "Error: Please enter a valid URL.")
            return
            
        # اگر پروتکل مشخص نشده، https را پیش فرض قرار می‌دهیم
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # ذخیره آدرس شروع برای استفاده در گزارش‌ها
        self.start_url = url
        
        # دریافت و اعتبارسنجی حداکثر عمق خزش
        max_depth_text = self.max_depth_entry.get().strip()
        try:
            max_depth = int(max_depth_text)
            if max_depth < 0:
                self._clear_output()
                messagebox.showerror("خطا", "مقدار عمق خزش باید یک عدد صحیح غیرمنفی باشد.")
                return
        except ValueError:
            self._clear_output()
            messagebox.showerror("خطا", "لطفاً یک عدد صحیح برای حداکثر عمق خزش وارد کنید.")
            return
        
        # پاک کردن ناحیه خروجی
        self._clear_output()
        self._clear_tree_view()
        self.all_broken_links.clear()
        self.all_external_links_info.clear()
        self.link_report_area.delete(1.0, tk.END)
        
        # بررسی فایل سناریو
        scenario_file_path = self.scenario_file_entry.get().strip()
        if scenario_file_path:
            self.current_scenario = self._load_scenario(scenario_file_path)
            if self.current_scenario:
                scenario_name = self.current_scenario["name"]
                target_pattern = self.current_scenario["target_url_pattern"]
                self.output_text_area.insert(tk.END, f"سناریو '{scenario_name}' برای الگوی URL '{target_pattern}' بارگذاری شد.\n\n")
        else:
            self.current_scenario = None
        
        # تغییر به تب لاگ برای نمایش پیشرفت
        self.notebook.select(0)
        
        # تنظیم وضعیت رابط کاربری
        self._crawling_in_progress = True
        self.has_crawl_data = False
        self.save_reports_button.config(state=tk.DISABLED)
        self.start_button.config(state=tk.DISABLED)
        self.start_button.update_idletasks()
        
        # شروع crawling در thread جداگانه با استفاده از عمق تعیین شده توسط کاربر
        self.crawl_thread = threading.Thread(
            target=self._perform_crawl_threaded, 
            args=(url, max_depth),
            daemon=True
        )
        self.crawl_thread.start()

    def _execute_scenario_actions(self, page, actions):
        """
        اجرای اقدامات سناریو روی یک صفحه Playwright
        
        :param page: شیء صفحه Playwright که اقدامات روی آن اجرا می‌شوند
        :param actions: لیست اقدامات سناریو برای اجرا
        :return: True در صورت موفقیت، False در صورت شکست
        """
        if not actions or not isinstance(actions, list):
            self.ui_queue.put({
                'type': 'log',
                'text': "خطا: لیست اقدامات سناریو خالی یا نامعتبر است.\n"
            })
            return False
            
        for action_idx, action_obj in enumerate(actions):
            # بررسی ساختار اقدام
            if not isinstance(action_obj, dict) or 'type' not in action_obj:
                self.ui_queue.put({
                    'type': 'log',
                    'text': f"خطا: اقدام شماره {action_idx+1} فاقد فیلد 'type' است.\n"
                })
                return False
                
            action_type = action_obj['type']
            action_log = f"اجرای اقدام سناریو {action_idx+1}/{len(actions)}: {action_type}"
            
            try:
                if action_type == "FILL_INPUT":
                    # بررسی وجود فیلدهای لازم
                    if 'selector' not in action_obj or 'text' not in action_obj:
                        self.ui_queue.put({
                            'type': 'log',
                            'text': f"خطا: اقدام FILL_INPUT فاقد 'selector' یا 'text' است.\n"
                        })
                        return False
                        
                    selector = action_obj['selector']
                    text = action_obj['text']
                    action_log += f" در {self._get_short_selector_description(selector)} با مقدار {text}"
                    
                    self.ui_queue.put({
                        'type': 'log',
                        'text': f"{action_log} - شروع...\n"
                    })
                    
                    # پیدا کردن المنت با استفاده از انواع مختلف selector
                    element = self._get_element_by_selector(page, selector)
                    if not element:
                        self.ui_queue.put({
                            'type': 'log',
                            'text': f"خطا: المنت با selector '{selector}' پیدا نشد.\n"
                        })
                        return False
                    
                    # پر کردن فیلد
                    element.fill(text)
                    
                    self.ui_queue.put({
                        'type': 'log',
                        'text': f"{action_log} - موفق\n"
                    })
                    
                elif action_type == "CLICK_ELEMENT":
                    # بررسی وجود فیلدهای لازم
                    if 'selector' not in action_obj:
                        self.ui_queue.put({
                            'type': 'log',
                            'text': f"خطا: اقدام CLICK_ELEMENT فاقد 'selector' است.\n"
                        })
                        return False
                        
                    selector = action_obj['selector']
                    action_log += f" روی {self._get_short_selector_description(selector)}"
                    
                    self.ui_queue.put({
                        'type': 'log',
                        'text': f"{action_log} - شروع...\n"
                    })
                    
                    # پیدا کردن المنت با استفاده از انواع مختلف selector
                    element = self._get_element_by_selector(page, selector)
                    if not element:
                        self.ui_queue.put({
                            'type': 'log',
                            'text': f"خطا: المنت با selector '{selector}' پیدا نشد.\n"
                        })
                        return False
                    
                    # کلیک روی عنصر
                    element.click()
                    
                    self.ui_queue.put({
                        'type': 'log',
                        'text': f"{action_log} - موفق\n"
                    })
                    
                elif action_type == "CHECK_ELEMENT":
                    # بررسی وجود فیلدهای لازم
                    if 'selector' not in action_obj:
                        self.ui_queue.put({
                            'type': 'log',
                            'text': f"خطا: اقدام CHECK_ELEMENT فاقد 'selector' است.\n"
                        })
                        return False
                        
                    selector = action_obj['selector']
                    action_log += f" روی {self._get_short_selector_description(selector)}"
                    
                    self.ui_queue.put({
                        'type': 'log',
                        'text': f"{action_log} - شروع...\n"
                    })
                    
                    # پیدا کردن المنت با استفاده از انواع مختلف selector
                    element = self._get_element_by_selector(page, selector)
                    if not element:
                        self.ui_queue.put({
                            'type': 'log',
                            'text': f"خطا: المنت با selector '{selector}' پیدا نشد.\n"
                        })
                        return False
                    
                    # فعال کردن چک باکس
                    element.check()
                    
                    self.ui_queue.put({
                        'type': 'log',
                        'text': f"{action_log} - موفق\n"
                    })
                    
                elif action_type == "GOTO_URL":
                    # بررسی وجود فیلدهای لازم
                    if 'url' not in action_obj:
                        self.ui_queue.put({
                            'type': 'log',
                            'text': f"خطا: اقدام GOTO_URL فاقد 'url' است.\n"
                        })
                        return False
                        
                    url = action_obj['url']
                    action_log += f" به {url}"
                    
                    self.ui_queue.put({
                        'type': 'log',
                        'text': f"{action_log} - شروع...\n"
                    })
                    
                    # رفتن به URL
                    page.goto(url)
                    
                    self.ui_queue.put({
                        'type': 'log',
                        'text': f"{action_log} - موفق\n"
                    })
                    
                elif action_type == "WAIT_FOR_NAVIGATION":
                    # دریافت زمان انتظار (پیش‌فرض 30 ثانیه)
                    timeout = action_obj.get("timeout", 30000)
                    state = action_obj.get("state", "load")
                    action_log += f" با مهلت {timeout}ms و حالت {state}"
                    
                    self.ui_queue.put({
                        'type': 'log',
                        'text': f"{action_log} - شروع...\n"
                    })
                    
                    # انتظار برای بارگذاری صفحه
                    page.wait_for_load_state(state, timeout=timeout)
                    
                    self.ui_queue.put({
                        'type': 'log',
                        'text': f"{action_log} - موفق\n"
                    })
                    
                else:
                    # نوع اقدام ناشناخته
                    self.ui_queue.put({
                        'type': 'log',
                        'text': f"هشدار: نوع اقدام '{action_type}' پشتیبانی نمی‌شود و نادیده گرفته می‌شود.\n"
                    })
                    continue
                    
            except Exception as e:
                # ثبت خطای اقدام
                self.ui_queue.put({
                    'type': 'log',
                    'text': f"{action_log} - خطا: {str(e)}\n"
                })
                return False
                
        # همه اقدامات با موفقیت اجرا شدند
        self.ui_queue.put({
            'type': 'log',
            'text': f"تمام {len(actions)} اقدام سناریو با موفقیت اجرا شدند.\n"
        })
        return True

    def _get_element_by_selector(self, page, selector):
        """
        پیدا کردن المنت در صفحه با استفاده از انواع مختلف selector
        
        :param page: شیء صفحه Playwright
        :param selector: رشته selector (CSS، XPath یا get_by_xxx)
        :return: شیء المنت پیدا شده یا None در صورت شکست
        """
        try:
            # بررسی اگر selector یک عبارت get_by_ است
            if selector.startswith('get_by_'):
                # استخراج نام متد و پارامترهای آن
                method_pattern = re.compile(r'get_by_(\w+)\s*\((.*)\)')
                method_match = method_pattern.search(selector)
                
                if method_match:
                    method_name = method_match.group(1)
                    args_str = method_match.group(2)
                    
                    # استخراج پارامترهای متد با در نظر گرفتن نقل قول‌ها
                    params = self._parse_function_params(args_str)
                    
                    # فراخوانی متد مناسب بر اساس نام متد استخراج شده
                    if method_name == 'role':
                        role = params.get('positional', [None])[0]
                        if role is None:
                            self.ui_queue.put({
                                'type': 'log',
                                'text': f"خطا: پارامتر نقش (role) در {selector} پیدا نشد\n"
                            })
                            return None
                            
                        # حذف نقل قول‌ها از مقدار نقش
                        role = role.strip('"\'')
                        
                        # ساخت دیکشنری کی‌وُرد آرگومنت‌ها
                        kwargs = {}
                        for k, v in params.get('named', {}).items():
                            # حذف نقل قول‌ها از مقادیر رشته‌ای
                            if isinstance(v, str):
                                if v.startswith('"') or v.startswith("'"):
                                    v = v.strip('"\'')
                            # تبدیل مقادیر بولی رشته‌ای به بولی واقعی
                            elif isinstance(v, str) and v.lower() in ('true', 'false'):
                                v = (v.lower() == 'true')
                            kwargs[k] = v
                            
                        # استفاده از متد get_by_role با پارامترهای استخراج شده
                        return page.get_by_role(role, **kwargs)
                    
                    elif method_name == 'text':
                        text = params.get('positional', [None])[0]
                        if text is None:
                            self.ui_queue.put({
                                'type': 'log',
                                'text': f"خطا: پارامتر متن (text) در {selector} پیدا نشد\n"
                            })
                            return None
                            
                        # حذف نقل قول‌ها از متن
                        text = text.strip('"\'')
                        
                        # ساخت دیکشنری کی‌وُرد آرگومنت‌ها
                        kwargs = {}
                        for k, v in params.get('named', {}).items():
                            # تبدیل مقادیر بولی رشته‌ای به بولی واقعی
                            if isinstance(v, str):
                                if v.startswith('"') or v.startswith("'"):
                                    v = v.strip('"\'')
                                elif v.lower() in ('true', 'false'):
                                    v = (v.lower() == 'true')
                            kwargs[k] = v
                            
                        # استفاده از متد get_by_text با پارامترهای استخراج شده
                        return page.get_by_text(text, **kwargs)
                    
                    elif method_name == 'label':
                        label = params.get('positional', [None])[0]
                        if label is None:
                            self.ui_queue.put({
                                'type': 'log',
                                'text': f"خطا: پارامتر برچسب (label) در {selector} پیدا نشد\n"
                            })
                            return None
                            
                        # حذف نقل قول‌ها از برچسب
                        label = label.strip('"\'')
                        
                        # ساخت دیکشنری کی‌وُرد آرگومنت‌ها
                        kwargs = {}
                        for k, v in params.get('named', {}).items():
                            # تبدیل مقادیر بولی رشته‌ای به بولی واقعی
                            if isinstance(v, str):
                                if v.startswith('"') or v.startswith("'"):
                                    v = v.strip('"\'')
                                elif v.lower() in ('true', 'false'):
                                    v = (v.lower() == 'true')
                            kwargs[k] = v
                            
                        # استفاده از متد get_by_label با پارامترهای استخراج شده
                        return page.get_by_label(label, **kwargs)
                    
                    elif method_name == 'placeholder':
                        placeholder = params.get('positional', [None])[0]
                        if placeholder is None:
                            self.ui_queue.put({
                                'type': 'log',
                                'text': f"خطا: پارامتر placeholder در {selector} پیدا نشد\n"
                            })
                            return None
                            
                        # حذف نقل قول‌ها از placeholder
                        placeholder = placeholder.strip('"\'')
                        
                        # ساخت دیکشنری کی‌وُرد آرگومنت‌ها
                        kwargs = {}
                        for k, v in params.get('named', {}).items():
                            # تبدیل مقادیر بولی رشته‌ای به بولی واقعی
                            if isinstance(v, str):
                                if v.startswith('"') or v.startswith("'"):
                                    v = v.strip('"\'')
                                elif v.lower() in ('true', 'false'):
                                    v = (v.lower() == 'true')
                            kwargs[k] = v
                            
                        # استفاده از متد get_by_placeholder با پارامترهای استخراج شده
                        return page.get_by_placeholder(placeholder, **kwargs)
                    
                    elif method_name == 'test_id':
                        test_id = params.get('positional', [None])[0]
                        if test_id is None:
                            self.ui_queue.put({
                                'type': 'log',
                                'text': f"خطا: پارامتر test_id در {selector} پیدا نشد\n"
                            })
                            return None
                            
                        # حذف نقل قول‌ها از test_id
                        test_id = test_id.strip('"\'')
                        
                        # استفاده از متد get_by_test_id با پارامترهای استخراج شده
                        return page.get_by_test_id(test_id)

                    elif method_name == 'title':
                        title = params.get('positional', [None])[0]
                        if title is None:
                            self.ui_queue.put({
                                'type': 'log',
                                'text': f"خطا: پارامتر title در {selector} پیدا نشد\n"
                            })
                            return None
                            
                        # حذف نقل قول‌ها از title
                        title = title.strip('"\'')
                        
                        # ساخت دیکشنری کی‌وُرد آرگومنت‌ها
                        kwargs = {}
                        for k, v in params.get('named', {}).items():
                            # تبدیل مقادیر بولی رشته‌ای به بولی واقعی
                            if isinstance(v, str):
                                if v.startswith('"') or v.startswith("'"):
                                    v = v.strip('"\'')
                                elif v.lower() in ('true', 'false'):
                                    v = (v.lower() == 'true')
                            kwargs[k] = v
                            
                        # استفاده از متد get_by_title با پارامترهای استخراج شده
                        return page.get_by_title(title, **kwargs)
                    
                    elif method_name == 'alt_text':
                        alt_text = params.get('positional', [None])[0]
                        if alt_text is None:
                            self.ui_queue.put({
                                'type': 'log',
                                'text': f"خطا: پارامتر alt_text در {selector} پیدا نشد\n"
                            })
                            return None
                            
                        # حذف نقل قول‌ها از alt_text
                        alt_text = alt_text.strip('"\'')
                        
                        # ساخت دیکشنری کی‌وُرد آرگومنت‌ها
                        kwargs = {}
                        for k, v in params.get('named', {}).items():
                            # تبدیل مقادیر بولی رشته‌ای به بولی واقعی
                            if isinstance(v, str):
                                if v.startswith('"') or v.startswith("'"):
                                    v = v.strip('"\'')
                                elif v.lower() in ('true', 'false'):
                                    v = (v.lower() == 'true')
                            kwargs[k] = v
                            
                        # استفاده از متد get_by_alt_text با پارامترهای استخراج شده
                        return page.get_by_alt_text(alt_text, **kwargs)
                    
                    # لاگ هشدار برای selector های get_by_ ناشناخته
                    self.ui_queue.put({
                        'type': 'log',
                        'text': f"هشدار: نوع متد get_by_{method_name} پشتیبانی نمی‌شود. تلاش با locator ساده.\n"
                    })
            
            # پشتیبانی از سایر الگوهای locator
            elif selector.startswith('xpath=') or selector.startswith('//'):
                # تبدیل به xpath صریح
                xpath_selector = selector if selector.startswith('xpath=') else f"xpath={selector}"
                return page.locator(xpath_selector)
            
            elif selector.startswith('text=') or (selector.startswith('"') and selector.endswith('"')) or (selector.startswith("'") and selector.endswith("'")):
                # تبدیل به text selector صریح
                if selector.startswith('"') or selector.startswith("'"):
                    text_content = selector[1:-1]
                    text_selector = f"text={text_content}"
                else:
                    text_selector = selector
                return page.locator(text_selector)
            
            # در صورتی که الگوهای خاص تطبیق نداشتند یا selector یک CSS یا XPath ساده است
            return page.locator(selector)
            
        except Exception as e:
            self.ui_queue.put({
                'type': 'log',
                'text': f"خطا در پیدا کردن المنت با selector '{selector}': {str(e)}\n"
            })
            return None

    def _perform_crawl_threaded(self, start_url, max_depth=1):
        """
        انجام خزش در thread جداگانه برای جلوگیری از فریز UI
        """
        try:
            # ارسال پیام شروع
            self.ui_queue.put({
                'type': 'log',
                'text': f"Starting crawl from {start_url} with max depth {max_depth}...\n\n"
            })
            
            # بررسی تطابق سناریو با URL
            if self.current_scenario:
                target_pattern = self.current_scenario["target_url_pattern"]
                scenario_name = self.current_scenario["name"]
                
                # بررسی ساده برابری رشته‌ای (می‌تواند در آینده با الگوهای پیچیده‌تر گسترش یابد)
                if start_url == target_pattern or target_pattern in start_url:
                    self.ui_queue.put({
                        'type': 'log',
                        'text': f"اطلاعات: سناریو '{scenario_name}' برای {start_url} مطابقت دارد. اجرای سناریو شروع می‌شود...\n"
                    })
            
            # انجام crawling
            crawled_data = self._perform_crawl_worker(start_url, max_depth)
            
            # ارسال نتایج به UI
            self.ui_queue.put({
                'type': 'crawl_complete',
                'crawled_data': crawled_data,
                'start_url': start_url
            })
            
        except Exception as e:
            # ارسال خطا به UI
            error_text = f"Error during crawl: {str(e)}\n\n"
            error_text += "Troubleshooting:\n"
            error_text += "1. Check your internet connection\n"
            error_text += "2. Verify the website is accessible in a regular browser\n"
            error_text += "3. The website might be blocking automated browsers\n"
            error_text += "4. Try with a different website"
            
            self.ui_queue.put({
                'type': 'error',
                'text': error_text
            })

    def _perform_crawl_worker(self, start_url, max_depth=1):
        """
        کارگر اصلی crawling که در thread جداگانه اجرا می‌شود
        """
        # مقداردهی اولیه متغیرهای مرتبط با سناریو
        scenario_to_execute = None
        scenario_name_for_log = "N/A (No scenario loaded or matched)"
        
        # ایجاد صف برای آدرس‌های در انتظار بازدید
        queue_urls = deque([(start_url, 0, None)])  
        visited_urls = set()
        crawled_pages_data = {}
        base_domain = urlparse(start_url).netloc
        
        # راه‌اندازی مرورگر
        browser_message = "Initializing browser..." if not self.browser else "Using existing browser instance..."
        self.ui_queue.put({
            'type': 'log',
            'text': f"{browser_message}\n\n"
        })
        
        if not self._init_browser():
            raise Exception("Failed to initialize browser. Cannot continue crawling.")
        
        # بررسی تطابق سناریو با URL
        if self.current_scenario:
            target_pattern = self.current_scenario.get('target_url_pattern')
            loaded_scenario_name = self.current_scenario.get('name', 'Unnamed Scenario')
            
            # تطبیق URL با الگوی هدف سناریو
            url_matches_scenario = False
            if target_pattern:
                if start_url == target_pattern:  # تطابق دقیق
                    url_matches_scenario = True
                # می‌توان برای حالت‌های انطباق انعطاف‌پذیرتر، شرایط دیگری نیز اضافه کرد
                # elif start_url.startswith(target_pattern):  # الگو به عنوان پیشوند
                #     url_matches_scenario = True
            
            # اگر URL با الگوی سناریو تطابق داشت، آماده‌سازی برای اجرای سناریو
            if url_matches_scenario:
                scenario_to_execute = self.current_scenario
                scenario_name_for_log = loaded_scenario_name
                
                self.ui_queue.put({
                    'type': 'log',
                    'text': f"اطلاعات: سناریو '{scenario_name_for_log}' برای {start_url} مطابقت دارد. اجرای سناریو شروع می‌شود...\n"
                })
            else:
                self.ui_queue.put({
                    'type': 'log',
                    'text': f"اطلاعات: سناریو '{loaded_scenario_name}' با URL هدف '{start_url}' مطابقت ندارد و اجرا نخواهد شد.\n"
                })
        else:
            # اگر هیچ سناریویی بارگذاری نشده باشد
            self.ui_queue.put({
                'type': 'log',
                'text': f"اطلاعات: هیچ سناریویی بارگذاری نشده است. خزش عادی برای {start_url} انجام می‌شود.\n"
            })
        
        # اجرای سناریو فقط در صورت وجود سناریوی مطابق
        scenario_executed_successfully = False
        if scenario_to_execute:
            actions = scenario_to_execute.get('actions', [])
            
            page_for_scenario = None
            try:
                # ایجاد صفحه جدید برای اجرای سناریو
                page_for_scenario = self.browser_context.new_page()
                
                # رفتن به صفحه هدف برای اجرای سناریو
                self.ui_queue.put({
                    'type': 'log',
                    'text': f"بارگذاری صفحه هدف برای سناریو: {start_url}\n"
                })
                
                page_for_scenario.goto(start_url, wait_until='domcontentloaded')
                
                # اجرای اقدامات سناریو
                scenario_executed_successfully = self._execute_scenario_actions(page_for_scenario, actions)
                
                if scenario_executed_successfully:
                    self.ui_queue.put({
                        'type': 'log',
                        'text': f"اطلاعات: سناریو '{scenario_name_for_log}' با موفقیت اجرا شد.\n\n"
                    })
                    # حالا browser_context کوکی‌های لازم را دارد
                else:
                    self.ui_queue.put({
                        'type': 'log',
                        'text': f"خطا: سناریو '{scenario_name_for_log}' به طور کامل اجرا نشد.\n\n"
                    })
            except Exception as e_scenario:
                self.ui_queue.put({
                    'type': 'log',
                    'text': f"خطا در آماده‌سازی صفحه برای سناریو یا در طول اجرای سناریو: {str(e_scenario)}\n\n"
                })
            finally:
                # بستن صفحه استفاده شده برای اجرای سناریو
                if page_for_scenario:
                    page_for_scenario.close()
        
        # ادامه خزش معمولی
        pages_visited = 0
        
        try:
            while queue_urls:
                current_url, current_depth, parent_url = queue_urls.popleft()
                
                if current_url in visited_urls or current_depth > max_depth:
                    continue
                
                visited_urls.add(current_url)
                pages_visited += 1
                
                # ارسال پیام به UI
                self.ui_queue.put({
                    'type': 'log',
                    'text': f"Crawling ({pages_visited}): {current_url} (Depth: {current_depth})\n"
                })
                
                try:
                    page_info = self._fetch_page_info_with_playwright(current_url)
                    
                    title = page_info['title']
                    internal_links = page_info['internal_links']
                    external_links = page_info['external_links']
                    status_code = page_info['page_status_code']
                    
                    crawled_pages_data[current_url] = {
                        'title': title,
                        'status': 'Crawled',
                        'depth': current_depth,
                        'links_count': len(internal_links) + len(external_links),
                        'parent_url': parent_url,
                        'status_code': status_code,
                        'external_links': external_links
                    }
                    
                    # ارسال اطلاعات صفحه به UI
                    log_text = f"Title: {title}\n"
                    log_text += f"Status: {status_code}\n"
                    log_text += f"Found {len(internal_links)} internal links\n"
                    log_text += f"External links found: {len(external_links)}\n\n"
                    
                    self.ui_queue.put({
                        'type': 'log',
                        'text': log_text
                    })
                    
                    # اضافه کردن لینک‌های داخلی به صف
                    if current_depth < max_depth:
                        internal_links_count = 0
                        
                        for link in internal_links:
                            if link not in visited_urls:
                                queue_urls.append((link, current_depth + 1, current_url))
                                internal_links_count += 1
                                
                                if internal_links_count <= 10:
                                    self.ui_queue.put({
                                        'type': 'log',
                                        'text': f"    → Queued: {link}\n"
                                    })
                        
                        if internal_links_count > 10:
                            self.ui_queue.put({
                                'type': 'log',
                                'text': f"    ... and {internal_links_count - 10} more links\n"
                            })
                            
                        self.ui_queue.put({
                            'type': 'log',
                            'text': f"    Total internal links queued: {internal_links_count}\n\n"
                        })
                            
                except Exception as e:
                    crawled_pages_data[current_url] = {
                        'title': 'Error',
                        'status': f'Error: {str(e)}',
                        'depth': current_depth,
                        'links_count': 0,
                        'parent_url': parent_url,
                        'status_code': 'Error',
                        'external_links': []
                    }
                    
                    # Use a temporary list for broken links in worker thread
                    # self.all_broken_links.append((current_url, current_url, 'Error')) 
                    self.ui_queue.put({
                        'type': 'log',
                        'text': f"Error processing page: {str(e)}\n\n"
                    })
            
            # پیام پایان crawling
            self.ui_queue.put({
                'type': 'log',
                'text': "=" * 50 + "\n"
            })
            self.ui_queue.put({
                'type': 'log',
                'text': f"Crawl finished. Visited {pages_visited} page(s).\n\n"
            })
            
            # بررسی لینک‌های خارجی
            self._check_external_links_threaded(crawled_pages_data)
            
            return crawled_pages_data
            
        except Exception as e:
            raise e

    def _check_external_links_threaded(self, crawled_pages_data):
        """
        بررسی لینک‌های خارجی در thread جداگانه
        """
        unique_external_urls_to_check = set()
        
        # جمع‌آوری تمام لینک‌های خارجی منحصر به فرد
        for page_url, page_data in crawled_pages_data.items():
            external_links = page_data.get('external_links', [])
            for ext_url in external_links:
                # اطمینان از اینکه فقط لینک‌های HTTP/HTTPS بررسی می‌شوند
                parsed_url = urlparse(ext_url)
                if parsed_url.scheme in ('http', 'https'):
                    unique_external_urls_to_check.add(ext_url)
        
        # لیست‌های موقت برای نگهداری نتایج بررسی در thread
        temp_all_external_links_info = []
        temp_all_broken_links = []
        
        if unique_external_urls_to_check:
            self.ui_queue.put({
                'type': 'log',
                'text': f"Checking status of {len(unique_external_urls_to_check)} unique external links in background...\n"
            })
            
            results_queue_ext = queue.Queue()
            threads_ext = []
            
            for ext_url in unique_external_urls_to_check:
                thread = threading.Thread(
                    target=self._check_link_status_worker,
                    args=(ext_url, results_queue_ext)
                )
                threads_ext.append(thread)
                thread.start()
            
            for thread in threads_ext:
                thread.join()
            
            url_status_map = {}
            
            while not results_queue_ext.empty():
                checked_url, status = results_queue_ext.get()
                url_status_map[checked_url] = status
            
            # یافتن صفحات منبع برای هر لینک خارجی بررسی شده
            for page_url, page_data in crawled_pages_data.items():
                for ext_url in page_data.get('external_links', []):
                    if ext_url in url_status_map:
                        status = url_status_map[ext_url]
                        temp_all_external_links_info.append((page_url, ext_url, status))
                        
                        # افزودن لینک‌های شکسته به گزارش (کدهای 4xx یا 5xx یا خطاها)
                        if (isinstance(status, int) and 400 <= status < 600) or isinstance(status, str) and "Error" in status:
                            temp_all_broken_links.append((page_url, ext_url, status))
            
            # ارسال اطلاعات لینک‌ها به UI
            self.ui_queue.put({
                'type': 'update_links',
                'broken_links': temp_all_broken_links,
                'external_links': temp_all_external_links_info
            })
            
            self.ui_queue.put({
                'type': 'log',
                'text': "External link status checking complete.\n"
            })
        else:
            self.ui_queue.put({
                'type': 'log',
                'text': "No external links found to check.\n"
            })
            # ارسال لیست‌های خالی در صورت نبود لینک خارجی
            self.ui_queue.put({
                'type': 'update_links',
                'broken_links': [],
                'external_links': []
            })

    def _check_link_status_worker(self, url_to_check, output_queue):
        """
        تابع کارگر برای بررسی وضعیت یک لینک خارجی در رشته جداگانه
        
        :param url_to_check: آدرس لینک برای بررسی
        :param output_queue: صف برای ذخیره نتایج
        """
        try:
            # ابتدا با درخواست HEAD سعی می‌کنیم
            response = requests.head(url_to_check, allow_redirects=True, timeout=10)
            status_code = response.status_code
        except requests.exceptions.Timeout:
            status_code = "Error: Timeout"
        except requests.exceptions.ConnectionError:
            status_code = "Error: ConnectionFailed"
        except requests.exceptions.TooManyRedirects:
            status_code = "Error: TooManyRedirects"
        except requests.exceptions.RequestException:
            # اگر HEAD با خطا مواجه شد، با GET امتحان می‌کنیم
            try:
                response = requests.get(url_to_check, stream=True, timeout=10)
                # فقط هدرها را دریافت می‌کنیم و اتصال را می‌بندیم
                response.close()
                status_code = response.status_code
            except Exception:
                status_code = "Error: RequestFailed"
        
        # افزودن نتیجه به صف نتایج
        output_queue.put((url_to_check, status_code))
    
    def _fetch_page_info_with_playwright(self, url):
        """
        استفاده از Playwright برای دریافت عنوان صفحه، پیوندها و کد وضعیت HTTP
        با استفاده از زمینه مرورگر موجود
        
        :param url: آدرس وب‌سایت
        :return: دیکشنری حاوی عنوان صفحه، لیست پیوندهای داخلی و خارجی و کد وضعیت HTTP
        """
        if not self.browser_context:
            raise Exception("Browser context is not initialized")
            
        page = None
        try:
            # ایجاد صفحه جدید در زمینه مرورگر موجود
            page = self.browser_context.new_page()
            
            # استفاده از استراتژی بارگذاری domcontentloaded برای سرعت بیشتر
            # ذخیره پاسخ برای دریافت کد وضعیت HTTP
            response = page.goto(url, wait_until='domcontentloaded')
            
            # دریافت کد وضعیت HTTP
            status_code = response.status if response else "N/A"
            
            # اجازه دادن به صفحه برای بارگذاری کامل
            try:
                page.wait_for_load_state('networkidle', timeout=10000)
            except:
                # اگر بارگذاری networkidle با مشکل مواجه شد، ادامه می‌دهیم
                pass
            
            # دریافت عنوان صفحه
            title = page.title()
            
            # استخراج تمام پیوندها
            link_elements = page.query_selector_all("a[href]")
            
            # دریافت آدرس کامل صفحه فعلی برای تبدیل آدرس‌های نسبی
            base_url = page.url
            
            # استخراج و تبدیل آدرس‌ها
            raw_links = []
            for element in link_elements:
                href = element.get_attribute('href')
                if href:
                    raw_links.append(href)
            
            # تبدیل آدرس‌های نسبی به مطلق و حذف آدرس‌های تکراری
            unique_links = set()
            for href in raw_links:
                absolute_url = self._normalize_url(href, base_url)
                if absolute_url:  # فقط آدرس‌های معتبر (غیر None) اضافه می‌شوند
                    unique_links.add(absolute_url)
            
            # مرتب‌سازی پیوندها برای نمایش بهتر
            sorted_links = sorted(list(unique_links))
            
            # تشخیص لینک‌های داخلی و خارجی
            bd = urlparse(base_url).netloc
            internal_links = []
            external_links = []
            
            for link in sorted_links:
                parsed_link = urlparse(link)
                # فقط لینک‌های HTTP و HTTPS را بررسی می‌کنیم
                if parsed_link.scheme in ('http', 'https'):
                    if parsed_link.netloc == bd:
                        internal_links.append(link)
                    else:
                        external_links.append(link)
            
            return {
                'title': title,
                'internal_links': internal_links,
                'external_links': external_links,
                'page_status_code': status_code
            }
                
        except TimeoutError as te:
            # در صورت تایم‌اوت، سعی در دریافت عنوان و پیوندها در هر صورت
            try:
                title = page.title() if page else "Unknown"
                status_code = "Timeout"  # کد وضعیت برای تایم‌اوت
                
                # تلاش برای استخراج پیوندها حتی در صورت بارگذاری ناقص صفحه
                link_elements = page.query_selector_all("a[href]") if page else []
                base_url = page.url if page else url
                
                raw_links = []
                for element in link_elements:
                    href = element.get_attribute('href')
                    if href:
                        raw_links.append(href)
                
                unique_links = set()
                for href in raw_links:
                    absolute_url = self._normalize_url(href, base_url)
                    if absolute_url:  # فقط آدرس‌های معتبر (غیر None) اضافه می‌شوند
                        unique_links.add(absolute_url)
                
                sorted_links = sorted(list(unique_links))
                
                # تشخیص لینک‌های داخلی و خارجی
                bd = urlparse(base_url).netloc
                internal_links = []
                external_links = []
                
                for link in sorted_links:
                    parsed_link = urlparse(link)
                    # فقط لینک‌های HTTP و HTTPS را بررسی می‌کنیم
                    if parsed_link.scheme in ('http', 'https'):
                        if parsed_link.netloc == bd:
                            internal_links.append(link)
                        else:
                            external_links.append(link)
                
                return {
                    'title': f"{title} (Note: Page loaded partially)",
                    'internal_links': internal_links,
                    'external_links': external_links,
                    'page_status_code': status_code
                }
            except:
                raise Exception(f"Timeout after 60 seconds. The website '{url}' is taking too long to respond.")
                
        except Error as e:
            # تلاش برای استخراج کد خطا از متن خطا
            error_message = str(e)
            status_code = "Error"
            
            # بررسی آیا کد خطای HTTP در پیام خطا آمده است
            if "status=" in error_message:
                try:
                    status_part = error_message.split("status=")[1]
                    status_code = status_part.split()[0]  # گرفتن عدد بعد از status=
                except:
                    pass
            
            raise Exception(f"Playwright error: {error_message}")
        finally:
            # بستن صفحه پس از اتمام کار، اما نگه داشتن مرورگر و زمینه آن
            if page:
                try:
                    page.close()
                except:
                    pass  # در صورت بروز خطا در بستن صفحه، آن را نادیده می‌گیریم
    
    def _normalize_url(self, href, base_url):
        """
        تبدیل آدرس‌های نسبی به آدرس‌های مطلق و فیلتر کردن آدرس‌های غیر استاندارد
        
        :param href: آدرس پیوند
        :param base_url: آدرس پایه صفحه
        :return: آدرس مطلق یا None برای آدرس‌های غیر استاندارد
        """
        # حذف لنگرها (fragments) از آدرس
        href = href.split('#')[0]
        
        # رد کردن آدرس‌های جاوااسکریپت، تلفن، ایمیل و غیره
        if href.startswith(('javascript:', 'tel:', 'mailto:', 'ftp:', 'file:', 'sms:', 'skype:', 'whatsapp:')):
            return None
                            
        # اگر آدرس خالی باشد، بازگشت به صفحه فعلی است
        if not href:
            return base_url
            
        # تبدیل آدرس نسبی به مطلق
        absolute_url = urljoin(base_url, href)
        
        # بررسی طرح آدرس - فقط http و https را قبول می‌کنیم
        parsed_url = urlparse(absolute_url)
        if parsed_url.scheme not in ('http', 'https'):
            return None
            
        # حذف پارامترهای اضافی اگر لازم است (اختیاری)
        clean_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
        if parsed_url.query:
            clean_url += f"?{parsed_url.query}"
            
        return clean_url
    
    def _display_crawl_results_as_tree(self, crawled_pages_data, start_url):
        """
        نمایش نتایج خزش به صورت ساختار درختی
        
        :param crawled_pages_data: دیکشنری حاوی اطلاعات صفحات خزش شده
        :param start_url: آدرس شروع خزش
        """
        # پاکسازی نمای درختی قبلی
        self._clear_tree_view()
        
        # ایجاد treeview جدید در فریم نتیجه با افزودن ستون کد وضعیت HTTP
        self.tree = ttk.Treeview(self.result_frame, columns=("title", "url", "status_code", "depth", "links"), show="tree headings")
        
        # تنظیم عناوین ستون‌ها
        self.tree.heading("#0", text="Page Structure")
        self.tree.heading("title", text="Title")
        self.tree.heading("url", text="URL")
        self.tree.heading("status_code", text="Status")  # عنوان ستون کد وضعیت HTTP
        self.tree.heading("depth", text="Depth")
        self.tree.heading("links", text="Links")
        
        # تنظیم عرض ستون‌ها
        self.tree.column("#0", width=150)
        self.tree.column("title", width=200)
        self.tree.column("url", width=250)
        self.tree.column("status_code", width=60, anchor='center')  # عرض ستون کد وضعیت
        self.tree.column("depth", width=50, anchor='center')
        self.tree.column("links", width=50, anchor='center')
        
        # اضافه کردن اسکرول‌بار
        tree_vsb = ttk.Scrollbar(self.result_frame, orient="vertical", command=self.tree.yview)
        tree_hsb = ttk.Scrollbar(self.result_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=tree_vsb.set, xscrollcommand=tree_hsb.set)
        
        # چیدمان treeview و اسکرول‌بارها
        self.tree.grid(column=0, row=0, sticky='nsew')
        tree_vsb.grid(column=1, row=0, sticky='ns')
        tree_hsb.grid(column=0, row=1, sticky='ew')
        
        # تنظیم grid برای فریم نتیجه
        self.result_frame.columnconfigure(0, weight=1)
        self.result_frame.rowconfigure(0, weight=1)
        
        # ساختن دیکشنری برای ذخیره فرزندان هر صفحه
        children_by_parent = {}
        orphaned_pages = []
        
        # پیدا کردن همه فرزندان هر صفحه
        for url, data in crawled_pages_data.items():
            parent_url = data['parent_url']
            
            if parent_url is None and url == start_url:
                # این همان صفحه ریشه است
                continue
            elif parent_url is None or parent_url not in crawled_pages_data:
                # صفحاتی که والد ندارند یا والد آنها خزش نشده
                orphaned_pages.append(url)
            else:
                # افزودن این صفحه به لیست فرزندان والدش
                if parent_url not in children_by_parent:
                    children_by_parent[parent_url] = []
                children_by_parent[parent_url].append(url)
        
        # دیکشنری برای ذخیره شناسه‌های treeview
        items_by_url = {}
        
        # تابع بازگشتی برای افزودن گره‌ها به درخت
        def _add_nodes_to_tree(parent_item_id, current_url):
            data = crawled_pages_data[current_url]
            
            # افزودن گره فعلی به درخت - با ستون کد وضعیت
            item_id = self.tree.insert(
                parent_item_id, 'end',
                text=data['title'],
                values=(
                    data['title'],
                    current_url,
                    data.get('status_code', 'N/A'),  # افزودن کد وضعیت HTTP
                    data['depth'],
                    data.get('links_count', 0)
                )
            )
            items_by_url[current_url] = item_id
            
            # افزودن تمام فرزندان به صورت بازگشتی
            if current_url in children_by_parent:
                for child_url in children_by_parent[current_url]:
                    _add_nodes_to_tree(item_id, child_url)
        
        # شروع با صفحه ریشه
        root_item = self.tree.insert('', 'end', text=crawled_pages_data[start_url]['title'],
                                    values=(
                                        crawled_pages_data[start_url]['title'],
                                        start_url,
                                        crawled_pages_data[start_url].get('status_code', 'N/A'),  # افزودن کد وضعیت HTTP
                                        0,
                                        crawled_pages_data[start_url].get('links_count', 0)
                                    ))
        items_by_url[start_url] = root_item
        
        # افزودن فرزندان صفحه ریشه
        if start_url in children_by_parent:
            for child_url in children_by_parent[start_url]:
                _add_nodes_to_tree(root_item, child_url)
        
        # افزودن صفحات یتیم (بدون والد)
        for url in orphaned_pages:
            data = crawled_pages_data[url]
            orphan_item = self.tree.insert(
                '', 'end',
                text=data['title'],
                values=(
                    data['title'],
                    url,
                    data.get('status_code', 'N/A'),  # افزودن کد وضعیت HTTP
                    data['depth'],
                    data.get('links_count', 0)
                )
            )
            items_by_url[url] = orphan_item
            
            # افزودن فرزندان صفحات یتیم
            if url in children_by_parent:
                for child_url in children_by_parent[url]:
                    _add_nodes_to_tree(orphan_item, child_url)
        
        # باز کردن نمای درختی برای نمایش کامل
        self.tree.item(root_item, open=True)
        
        # تغییر به تب نمای درختی
        self.notebook.select(1)
    
    def _display_link_report(self):
        """
        نمایش گزارش لینک‌های خارجی و شکسته در تب Link Report
        """
        self.link_report_area.delete(1.0, tk.END)
        
        # بخش لینک‌های شکسته
        self.link_report_area.insert(tk.END, "Broken Links Found:\n")
        self.link_report_area.insert(tk.END, "-" * 50 + "\n")
        
        if not self.all_broken_links:
            self.link_report_area.insert(tk.END, "None\n\n")
        else:
            # مرتب‌سازی لینک‌های شکسته بر اساس کد وضعیت
            sorted_broken_links = sorted(self.all_broken_links, key=lambda x: str(x[2]))
            
            # گروه‌بندی لینک‌های شکسته بر اساس نوع خطا
            broken_by_status = {}
            for src, url, st in sorted_broken_links:
                status_key = str(st)
                if status_key not in broken_by_status:
                    broken_by_status[status_key] = []
                broken_by_status[status_key].append((src, url))
            
            # نمایش لینک‌های شکسته گروه‌بندی شده
            for status, links in sorted(broken_by_status.items()):
                self.link_report_area.insert(tk.END, f"Status: {status} - {len(links)} link(s)\n")
                for src, url in links:
                    self.link_report_area.insert(
                        tk.END,
                        f"  • On page [{src}]: Link [{url}]\n"
                    )
                self.link_report_area.insert(tk.END, "\n")
        
        # بخش لینک‌های خارجی
        self.link_report_area.insert(tk.END, "External Links Summary:\n")
        self.link_report_area.insert(tk.END, "-" * 50 + "\n")
        
        if not self.all_external_links_info:
            self.link_report_area.insert(tk.END, "None\n")
        else:
            # شمارش تعداد لینک‌های خارجی بر اساس دامنه
            domain_counts = {}
            status_success_count = 0
            status_error_count = 0
            
            for _, url, status in self.all_external_links_info:
                # شمارش دامنه‌ها
                domain = urlparse(url).netloc
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
                
                # شمارش وضعیت‌ها
                if isinstance(status, int) and 200 <= status < 400:
                    status_success_count += 1
                else:
                    status_error_count += 1
            
            # نمایش خلاصه آماری
            self.link_report_area.insert(tk.END, f"Total unique domains: {len(domain_counts)}\n")
            self.link_report_area.insert(tk.END, f"Total external links: {len(self.all_external_links_info)}\n")
            self.link_report_area.insert(tk.END, f"Successful links (2xx/3xx): {status_success_count}\n")
            self.link_report_area.insert(tk.END, f"Problem links (4xx/5xx/Errors): {status_error_count}\n\n")
            
            # نمایش دامنه‌ها به ترتیب تعداد
            self.link_report_area.insert(tk.END, "Domains (by frequency):\n")
            for domain, count in sorted(domain_counts.items(), key=lambda x: x[1], reverse=True):
                self.link_report_area.insert(tk.END, f"  • {domain}: {count} link(s)\n")
            
            self.link_report_area.insert(tk.END, "\n")
            
            # نمایش وضعیت‌های مختلف
            status_counts = {}
            for _, _, st in self.all_external_links_info:
                status_key = str(st)
                status_counts[status_key] = status_counts.get(status_key, 0) + 1
            
            self.link_report_area.insert(tk.END, "Status Codes (by frequency):\n")
            for status, count in sorted(status_counts.items(), key=lambda x: int(x[1]), reverse=True):
                self.link_report_area.insert(tk.END, f"  • {status}: {count} link(s)\n")
            
            # اضافه کردن بخش نمایش جزئیات لینک‌ها
            self.link_report_area.insert(tk.END, "\nDetailed External Links:\n")
            self.link_report_area.insert(tk.END, "-" * 50 + "\n")
            
            # گروه‌بندی بر اساس دامنه
            links_by_domain = {}
            for src, url, st in self.all_external_links_info:
                domain = urlparse(url).netloc
                if domain not in links_by_domain:
                    links_by_domain[domain] = []
                links_by_domain[domain].append((src, url, st))
            
            # نمایش لینک‌ها بر اساس دامنه
            for domain, links in sorted(links_by_domain.items()):
                self.link_report_area.insert(tk.END, f"Domain: {domain} ({len(links)} links)\n")
                # مرتب‌سازی بر اساس وضعیت
                sorted_links = sorted(links, key=lambda x: str(x[2]))
                for src, url, st in sorted_links:
                    status_display = f"[{st}]"
                    if isinstance(st, int):
                        if 200 <= st < 300:
                            status_display = f"[{st} ✓]"
                        elif 300 <= st < 400:
                            status_display = f"[{st} ⟳]"  # Redirect
                        elif 400 <= st < 500:
                            status_display = f"[{st} ✗]"  # Client Error
                        elif 500 <= st < 600:
                            status_display = f"[{st} ‼]"  # Server Error
                    elif isinstance(st, str) and "Error" in st:
                        status_display = f"[{st} ‼]"
                        
                    self.link_report_area.insert(
                        tk.END,
                        f"  • {status_display} {url}\n    Source: {src}\n"
                    )
                self.link_report_area.insert(tk.END, "\n")

        # سوئیچ به تب گزارش لینک
        self.notebook.select(self.link_report_tab_index)
    
    def _clear_tree_view(self):
        """
        پاکسازی نمای درختی قبلی
        """
        # حذف treeview قبلی اگر وجود داشته باشد
        if hasattr(self, 'tree') and self.tree:
            for widget in self.result_frame.winfo_children():
                widget.destroy()
            self.tree = None
    
    def _clear_output(self):
        """
        پاک کردن محتوای ناحیه خروجی
        """
        self.output_text_area.delete(1.0, tk.END)

    def _process_ui_queue(self):
        """
        پردازش پیام‌های دریافتی از thread crawling برای به‌روزرسانی UI
        """
        try:
            while True:
                try:
                    message = self.ui_queue.get_nowait()
                    self._handle_ui_message(message)
                except queue.Empty:
                    break
        except Exception as e:
            # Log any error during UI queue processing to avoid silent failures
            print(f"Error processing UI queue: {e}") 
        
        # تکرار این فرآیند هر 100 میلی‌ثانیه
        self.master.after(100, self._process_ui_queue)

    def _handle_ui_message(self, message):
        """
        مدیریت پیام‌های مختلف از thread crawling
        """
        msg_type = message['type']
        
        if msg_type == 'log':
            self.output_text_area.insert(tk.END, message['text'])
            self.output_text_area.update_idletasks()
            # اسکرول به انتها
            self.output_text_area.see(tk.END)
            
        elif msg_type == 'crawl_complete':
            # crawling تمام شد
            self._crawling_in_progress = False
            self.has_crawl_data = True
            self.start_button.config(state=tk.NORMAL)
            self.save_reports_button.config(state=tk.NORMAL)  # فعال کردن دکمه ذخیره گزارش‌ها
            self.start_button.update_idletasks()
            self.save_reports_button.update_idletasks()
            
            # نمایش نتایج
            self.crawled_pages_data = message['crawled_data']
            self.start_url = message['start_url']
            
            # نمایش نتایج درختی و گزارش لینک
            self._display_crawl_results_as_tree(self.crawled_pages_data, self.start_url)
            self._display_link_report()
            
            # ذخیره خودکار گزارش‌ها
            self._auto_save_reports()
            
        elif msg_type == 'update_links':
            # به‌روزرسانی لیست لینک‌ها
            self.all_broken_links = message['broken_links']
            self.all_external_links_info = message['external_links']
            
        elif msg_type == 'error':
            # مدیریت خطا
            self._clear_output()
            self.output_text_area.insert(tk.END, message['text'])
            self._crawling_in_progress = False
            self.start_button.config(state=tk.NORMAL)
            self.start_button.update_idletasks()
    
    def _save_reports_to_directory(self, target_base_directory, site_url_for_naming):
        """
        ذخیره گزارش‌ها در دایرکتوری مشخص شده
        
        :param target_base_directory: دایرکتوری پایه برای ذخیره گزارش‌ها
        :param site_url_for_naming: آدرس سایت برای استفاده در نام‌گذاری پوشه
        :return: (موفقیت/شکست, مسیر کامل ذخیره یا پیام خطا)
        """
        try:
            # ایجاد نام پوشه با استفاده از دامنه و زمان فعلی
            domain = urlparse(site_url_for_naming).netloc.replace(".", "_")
            if not domain:  # اگر دامنه خالی باشد، از یک نام پیش‌فرض استفاده کنیم
                domain = "website"
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            report_dir_name = f"{domain}_{timestamp}_report"
            report_dir_path = os.path.join(target_base_directory, report_dir_name)
            
            # ایجاد دایرکتوری گزارش
            os.makedirs(report_dir_path, exist_ok=True)
            
            # ذخیره گزارش لاگ
            log_file_path = os.path.join(report_dir_path, "crawl_log.txt")
            with open(log_file_path, "w", encoding="utf-8") as log_file:
                log_content = self.output_text_area.get(1.0, tk.END)
                log_file.write(log_content)
            
            # ذخیره داده‌های ساختار سایت (درخت)
            structure_file_path = os.path.join(report_dir_path, "site_structure_data.json")
            with open(structure_file_path, "w", encoding="utf-8") as structure_file:
                # اگر URL حاوی متادیتا باشد، باید آن را قابل سریالایز کنیم
                serializable_data = {}
                for url, data in self.crawled_pages_data.items():
                    serializable_data[url] = {
                        'title': data.get('title', ''),
                        'status': data.get('status', ''),
                        'depth': data.get('depth', 0),
                        'links_count': data.get('links_count', 0),
                        'parent_url': data.get('parent_url', None),
                        'status_code': str(data.get('status_code', '')),
                        # لینک‌های خارجی را ذخیره نمی‌کنیم چون ممکن است بزرگ باشند
                    }
                json.dump(serializable_data, structure_file, ensure_ascii=False, indent=2)
            
            # ذخیره گزارش لینک
            link_report_file_path = os.path.join(report_dir_path, "link_analysis_report.txt")
            with open(link_report_file_path, "w", encoding="utf-8") as link_file:
                link_content = self.link_report_area.get(1.0, tk.END)
                link_file.write(link_content)
                
            # ذخیره خلاصه گزارش
            summary_file_path = os.path.join(report_dir_path, "summary_report.txt")
            with open(summary_file_path, "w", encoding="utf-8") as summary_file:
                summary_content = (
                    f"Website Test Report Summary\n"
                    f"=========================\n\n"
                    f"URL: {self.start_url}\n"
                    f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"Pages Crawled: {len(self.crawled_pages_data)}\n"
                    f"External Links Found: {len(self.all_external_links_info)}\n"
                    f"Broken Links Found: {len(self.all_broken_links)}\n\n"
                    f"This report directory contains:\n"
                    f"- crawl_log.txt: Detailed log of the crawling process\n"
                    f"- site_structure_data.json: Data structure of the crawled website\n"
                    f"- link_analysis_report.txt: Analysis of all external and broken links\n"
                )
                summary_file.write(summary_content)
                
            return True, report_dir_path
            
        except Exception as e:
            return False, str(e)
    
    def _handle_save_reports(self):
        """
        ذخیره گزارش‌های تولید شده در پوشه انتخابی کاربر
        """
        # بررسی وجود داده‌های خزش
        if not self.has_crawl_data:
            messagebox.showinfo("اطلاعات", "هیچ گزارشی برای ذخیره وجود ندارد. لطفاً ابتدا یک خزش وب را انجام دهید.")
            return
        
        # دریافت دایرکتوری مقصد از کاربر
        target_dir = filedialog.askdirectory(title="انتخاب محل ذخیره گزارش‌ها")
        if not target_dir:
            return  # کاربر عملیات را لغو کرده است
        
        # استفاده از متد جدید برای ذخیره گزارش‌ها
        success, result_message = self._save_reports_to_directory(target_dir, self.start_url)
        
        if success:
            # نمایش پیام موفقیت
            messagebox.showinfo(
                "گزارش‌ها ذخیره شدند",
                f"گزارش‌ها با موفقیت در دایرکتوری زیر ذخیره شدند:\n{result_message}"
            )
        else:
            # نمایش خطا در صورت بروز مشکل
            messagebox.showerror(
                "خطا در ذخیره گزارش‌ها",
                f"خطایی هنگام ذخیره گزارش‌ها رخ داد:\n{result_message}"
            )

    def _auto_save_reports(self):
        """
        ذخیره خودکار گزارش‌ها در دایرکتوری پیش‌فرض
        """
        if not self.has_crawl_data:
            return
            
        success, result = self._save_reports_to_directory(self.default_auto_save_dir, self.start_url)
        
        if success:
            self.output_text_area.insert(tk.END, f"اطلاعات: گزارش‌ها به صورت خودکار در مسیر زیر ذخیره شدند:\n{result}\n\n")
        else:
            self.output_text_area.insert(tk.END, f"خطا: ذخیره خودکار گزارش‌ها با مشکل مواجه شد: {result}\n\n")
        
        # اسکرول به انتهای لاگ
        self.output_text_area.see(tk.END)

    def _parse_function_params(self, params_str):
        """
        تجزیه پارامترهای یک تابع به صورت پارامترهای مستقیم و نام‌گذاری شده
        
        :param params_str: رشته حاوی پارامترهای تابع
        :return: دیکشنری حاوی پارامترهای موقعیتی و نام‌گذاری شده
        """
        if not params_str or params_str.strip() == '':
            return {'positional': [], 'named': {}}
        
        result = {'positional': [], 'named': {}}
        
        # حالت مختلف برای نقل قول‌ها در پارامترها
        in_quotes = False
        quote_char = None
        current_param = ''
        params_list = []
        
        i = 0
        while i < len(params_str):
            char = params_str[i]
            
            # تشخیص نقل قول
            if char in ('"', "'") and (i == 0 or params_str[i-1] != '\\'):
                if not in_quotes:
                    in_quotes = True
                    quote_char = char
                elif char == quote_char:
                    in_quotes = False
                current_param += char
            # تشخیص جداکننده پارامترها
            elif char == ',' and not in_quotes:
                params_list.append(current_param.strip())
                current_param = ''
            else:
                current_param += char
            
            i += 1
        
        # اضافه کردن آخرین پارامتر
        if current_param.strip():
            params_list.append(current_param.strip())
        
        # جداسازی پارامترهای موقعیتی و نام‌گذاری شده
        for param in params_list:
            # بررسی اگر پارامتر نام‌گذاری شده است
            if '=' in param and not (param.startswith('"') or param.startswith("'")):
                key, value = param.split('=', 1)
                key = key.strip()
                value = value.strip()
                result['named'][key] = value
            else:
                result['positional'].append(param)
                
        return result
    
    def _get_short_selector_description(self, selector):
        """
        تولید یک توصیف کوتاه از selector برای نمایش در لاگ‌ها
        
        :param selector: رشته selector
        :return: توصیف کوتاه
        """
        # حداکثر طول خروجی
        max_length = 30
        
        if selector.startswith('get_by_role'):
            match = re.search(r'get_by_role\(["\']([^"\']+)["\'](?:.*?name=["\']([^"\']+)["\'])?', selector)
            if match:
                role = match.group(1)
                name = match.group(2) if match.group(2) else ""
                if name:
                    return f"{role} '{name}'"
                else:
                    return f"{role}"
        
        elif selector.startswith('get_by_text'):
            match = re.search(r'get_by_text\(["\']([^"\']+)["\']', selector)
            if match:
                text = match.group(1)
                if len(text) > max_length:
                    text = text[:max_length-3] + "..."
                return f"متن '{text}'"
        
        elif selector.startswith('get_by_label'):
            match = re.search(r'get_by_label\(["\']([^"\']+)["\']', selector)
            if match:
                label = match.group(1)
                if len(label) > max_length:
                    label = label[:max_length-3] + "..."
                return f"برچسب '{label}'"
        
        elif selector.startswith('get_by_placeholder'):
            match = re.search(r'get_by_placeholder\(["\']([^"\']+)["\']', selector)
            if match:
                placeholder = match.group(1)
                if len(placeholder) > max_length:
                    placeholder = placeholder[:max_length-3] + "..."
                return f"placeholder '{placeholder}'"
        
        elif selector.startswith('get_by_test_id'):
            match = re.search(r'get_by_test_id\(["\']([^"\']+)["\']', selector)
            if match:
                test_id = match.group(1)
                return f"test-id '{test_id}'"
                
        # کوتاه کردن selector برای نمایش بهتر در لاگ
        if len(selector) > max_length:
            selector = selector[:max_length-3] + "..."
            
        return selector


if __name__ == "__main__":
    root = tk.Tk()
    app = WebsiteTesterApp(root)
    root.mainloop() 