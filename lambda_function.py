import os
import json
import time
import traceback
import yagmail
import boto3
import glob
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, ElementClickInterceptedException

VP_LOGIN_URL = "https://gibson-hff.viewpointforcloud.com/account/login?ReturnUrl=%2F"
EARNINGS_URL = "https://gibson-hff.viewpointforcloud.com/employee/earnings"

def get_parameter(name, decrypt=True):
    """Get parameter from AWS SSM Parameter Store"""
    try:
        ssm = boto3.client('ssm', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
        response = ssm.get_parameter(Name=name, WithDecryption=decrypt)
        return response['Parameter']['Value']
    except Exception as e:
        print(f"Error getting parameter {name}: {e}")
        return None


def download_pdf_with_session(driver, pdf_url):
    """Download PDF using requests with session cookies from Selenium"""
    import requests
    
    print("📥 Downloading PDF with session...")
    
    # Get all cookies from Selenium
    selenium_cookies = driver.get_cookies()
    
    # Create requests session and add cookies
    session = requests.Session()
    for cookie in selenium_cookies:
        session.cookies.set(
            cookie['name'], 
            cookie['value'],
            domain=cookie.get('domain'),
            path=cookie.get('path', '/')
        )
    
    # Copy headers from Selenium
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'application/pdf,*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    })
    
    # Try to download the PDF
    try:
        response = session.get(pdf_url, allow_redirects=True, timeout=30)
        
        if response.status_code == 200:
            content = response.content
            
            # Check if it's actually a PDF
            if content.startswith(b'%PDF'):
                print(f"✅ Downloaded valid PDF, size: {len(content)} bytes")
                return content
            else:
                # Sometimes the server returns HTML with a meta refresh or JavaScript redirect
                print("⚠️ Got HTML instead of PDF, trying alternative approach...")
                
                # Check if there's a redirect in the HTML
                if b'window.location' in content or b'meta http-equiv="refresh"' in content:
                    print("📍 Found redirect in HTML, following it...")
                    
                    # Use Selenium to navigate and wait for the actual PDF
                    driver.get(pdf_url)
                    time.sleep(3)
                    
                    # Try to find the actual PDF URL in the page
                    try:
                        # Look for iframe or embed with PDF
                        pdf_elements = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='.pdf'], embed[src*='.pdf'], object[data*='.pdf']")
                        if pdf_elements:
                            actual_pdf_url = pdf_elements[0].get_attribute('src') or pdf_elements[0].get_attribute('data')
                            print(f"📎 Found actual PDF URL: {actual_pdf_url}")
                            
                            # Download the actual PDF
                            response = session.get(actual_pdf_url, allow_redirects=True)
                            if response.status_code == 200 and response.content.startswith(b'%PDF'):
                                print(f"✅ Downloaded valid PDF from iframe, size: {len(response.content)} bytes")
                                return response.content
                    except:
                        pass
                    
                    # Last resort: get the current URL after redirects
                    current_url = driver.current_url
                    if current_url != pdf_url:
                        print(f"📍 Redirected to: {current_url}")
                        response = session.get(current_url, allow_redirects=True)
                        if response.status_code == 200 and response.content.startswith(b'%PDF'):
                            print(f"✅ Downloaded valid PDF from redirect, size: {len(response.content)} bytes")
                            return response.content
                
                print("❌ Could not get PDF content")
                return None
        else:
            print(f"❌ HTTP error: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ Error downloading PDF: {e}")
        return None
    

def setup_driver():
    """Setup Chrome driver with Lambda-compatible options"""
    print("🔧 Setting up Chrome driver...")
    
    options = Options()
    options.binary_location = '/opt/chrome/chrome'
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-dev-tools')
    options.add_argument('--no-zygote')
    options.add_argument('--single-process')
    options.add_argument('--user-data-dir=/tmp/chrome-user-data')
    options.add_argument('--data-path=/tmp/chrome-data-path')
    options.add_argument('--disk-cache-dir=/tmp/chrome-cache')
    options.add_argument('--remote-debugging-port=9222')
    
    # Add more options for stability
    options.add_argument('--disable-software-rasterizer')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-setuid-sandbox')
    options.add_argument('--disable-features=VizDisplayCompositor')
    options.add_argument('--disable-background-timer-throttling')
    options.add_argument('--disable-backgrounding-occluded-windows')
    options.add_argument('--disable-renderer-backgrounding')
    options.add_argument('--disable-features=TranslateUI')
    options.add_argument('--disable-ipc-flooding-protection')
    options.add_argument('--force-color-profile=srgb')
    
    # Set window size to ensure elements are visible
    options.add_argument('--window-size=1920,1080')
    
    service = Service('/opt/chromedriver')
    
    try:
        driver = webdriver.Chrome(service=service, options=options)
        print("✅ Chrome driver created successfully")
        return driver
    except Exception as e:
        print(f"❌ Failed to create Chrome driver: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        raise

def wait_and_click(driver, element, use_js=False):
    """Click an element, using JavaScript if necessary"""
    try:
        if use_js:
            driver.execute_script("arguments[0].click();", element)
        else:
            element.click()
        return True
    except ElementClickInterceptedException:
        print("⚠️ Regular click intercepted, trying JavaScript click...")
        driver.execute_script("arguments[0].click();", element)
        return True

def login_and_download(username, password):
    """Login to Viewpoint and download the latest paystub"""
    print(f"👤 Logging in as {username}")
    driver = None
    
    try:
        driver = setup_driver()
        wait = WebDriverWait(driver, 15)
        
        # Test that Chrome is working
        print("🌐 Testing Chrome with Google...")
        driver.get("https://www.google.com")
        print(f"✅ Chrome working, title: {driver.title}")
        
        print(f"🌐 Navigating to login page: {VP_LOGIN_URL}")
        driver.get(VP_LOGIN_URL)
        print(f"📍 Current URL: {driver.current_url}")
        print(f"📄 Page title: {driver.title}")
        
        # Take screenshot for debugging
        screenshot_path = "/tmp/login_page.png"
        driver.save_screenshot(screenshot_path)
        print(f"📸 Screenshot saved to {screenshot_path}")
        
        # Click employee number option
        print("🔍 Looking for employee number option...")
        try:
            employee_num_btn = wait.until(EC.element_to_be_clickable((By.ID, "employeeNum")))
            print("✅ Found employee number button")
            wait_and_click(driver, employee_num_btn)
            print("✅ Clicked employee number button")
        except TimeoutException:
            print("❌ Timeout waiting for employee number button")
            print(f"Page source preview: {driver.page_source[:500]}...")
            raise
        
        # Wait for login form
        print("⏳ Waiting for login form elements...")
        time.sleep(2)  # Give form time to render
        
        try:
            employee_field = wait.until(EC.presence_of_element_located((By.ID, "employee-num")))
            print("✅ Found employee-num field")
            
            password_field = wait.until(EC.presence_of_element_located((By.ID, "password")))
            print("✅ Found password field")
            
            submit_button = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "button[type='submit']")))
            print("✅ Found submit button")
        except TimeoutException as e:
            print(f"❌ Timeout waiting for form elements: {e}")
            driver.save_screenshot("/tmp/form_timeout.png")
            raise
        
        # Fill credentials
        print("📝 Filling in credentials...")
        employee_field.clear()
        employee_field.send_keys(username)
        
        password_field.clear()
        password_field.send_keys(password)
        print("✅ Credentials filled")
        
        # Wait a bit for any client-side validation
        time.sleep(1)
        
        # Check if button is still disabled
        submit_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        is_disabled = submit_button.get_attribute("disabled")
        print(f"🔍 Submit button disabled status: {is_disabled}")
        
        # Try multiple approaches to submit the form
        print("🖱️ Attempting to submit form...")
        
        # Method 1: Try JavaScript click
        try:
            driver.execute_script("arguments[0].click();", submit_button)
            print("✅ Submitted via JavaScript click")
        except Exception as e1:
            print(f"⚠️ JavaScript click failed: {e1}")
            
            # Method 2: Try removing disabled attribute and clicking
            try:
                driver.execute_script("arguments[0].removeAttribute('disabled');", submit_button)
                time.sleep(0.5)
                submit_button.click()
                print("✅ Submitted after removing disabled attribute")
            except Exception as e2:
                print(f"⚠️ Remove disabled + click failed: {e2}")
                
                # Method 3: Try submitting the form directly
                try:
                    driver.execute_script("document.querySelector('form').submit();")
                    print("✅ Submitted via form.submit()")
                except Exception as e3:
                    print(f"⚠️ Form submit failed: {e3}")
                    
                    # Method 4: Try pressing Enter in password field
                    from selenium.webdriver.common.keys import Keys
                    password_field.send_keys(Keys.RETURN)
                    print("✅ Submitted via Enter key")
        
        print("⏳ Waiting for login to complete...")
        time.sleep(5)
        
        # Check if we're still on login page
        current_url = driver.current_url
        print(f"📍 Current URL after login attempt: {current_url}")
        
        if "login" in current_url.lower():
            print("⚠️ Still on login page, checking for error messages...")
            driver.save_screenshot("/tmp/login_failed.png")
            
            # Look for error messages
            try:
                error_elements = driver.find_elements(By.CSS_SELECTOR, ".alert, .error, .invalid-feedback")
                for elem in error_elements:
                    if elem.is_displayed() and elem.text:
                        print(f"❌ Error message found: {elem.text}")
            except:
                pass
            
            # If using test credentials, just continue
            if username == "YOUR_EMPLOYEE_NUMBER":
                print("⚠️ Using test credentials, skipping to test the rest of the flow...")
                return None
        
        # Navigate to earnings page
        print(f"🧭 Navigating to earnings page: {EARNINGS_URL}")
        driver.get(EARNINGS_URL)
        time.sleep(3)
        print(f"📍 Current URL: {driver.current_url}")
        
        # Check if redirected back to login
        if "login" in driver.current_url.lower():
            print("❌ Redirected back to login page - authentication failed")
            return None
        
        # Find paystub links
        print("⏳ Waiting for paystub links...")
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='Document/GetFile']")))
            links = driver.find_elements(By.CSS_SELECTOR, "a[href*='Document/GetFile']")
            print(f"✅ Found {len(links)} paystub links")
        except TimeoutException:
            print("❌ No paystub links found")
            driver.save_screenshot("/tmp/no_paystubs.png")
            # Try alternative selectors
            print("🔍 Trying alternative selectors...")
            links = driver.find_elements(By.CSS_SELECTOR, "a[href*='document'], a[href*='pdf'], a[href*='download']")
            if links:
                print(f"✅ Found {len(links)} alternative links")
            else:
                return None

        if not links:
            print("❌ No paystub links found.")
            return None

        # ---------- вставить начало нового блока ----------
        # Deduplicate links by their href attribute
        unique_links = []
        seen = set()
        for link in links:
            href = link.get_attribute("href")
            if href not in seen:
                unique_links.append(link)
                seen.add(href)
        # ---------- вставить конец нового блока ----------

        



        # Get the first (latest) paystub URL
        # Get the first (most recent) paystub
        pdf_url = unique_links[0].get_attribute("href")
        print(f"\n📎 Selected PDF URL: {pdf_url}")
        
        # Download PDF using enhanced method
        pdf_data = download_pdf_with_session(driver, pdf_url)
        
        if not pdf_data:
            print("⚠️ First method failed, trying direct Selenium download...")
            
            # Alternative: Use Selenium to trigger download
            original_window = driver.current_window_handle
            
            # Open link in new tab
            driver.execute_script("window.open(arguments[0], '_blank');", pdf_url)
            
            # Switch to new tab
            driver.switch_to.window(driver.window_handles[-1])
            time.sleep(5)
            
            # Check if PDF is displayed
            if "application/pdf" in driver.execute_script("return document.contentType || '';"):
                print("✅ PDF opened in browser")
                
                # Try to get PDF content from browser
                # This is tricky as PDFs are handled by browser plugins
                # We'll need to use the download approach
                
                # Close tab and switch back
                driver.close()
                driver.switch_to.window(original_window)
                
                # Use alternative download method
                print("📥 Attempting alternative download...")
                
                # Click the link to trigger browser download
                unique_links[0].click()
                time.sleep(5)
                
                # Check for downloaded file in /tmp
                import glob
                pdf_files = glob.glob("/tmp/*.pdf")
                if pdf_files:
                    newest_pdf = max(pdf_files, key=os.path.getctime)
                    with open(newest_pdf, 'rb') as f:
                        pdf_data = f.read()
                    print(f"✅ Found downloaded PDF: {newest_pdf}, size: {len(pdf_data)} bytes")
                    
                    # Clean up
                    os.remove(newest_pdf)
            else:
                # Close tab and switch back
                driver.close()
                driver.switch_to.window(original_window)
        
        if not pdf_data:
            print("❌ All download methods failed")
            return None
        
        # Verify we have valid PDF data
        if not pdf_data.startswith(b'%PDF'):
            print(f"⚠️ Downloaded data is not a valid PDF (starts with: {pdf_data[:20]})")
            
            # Save what we got for debugging
            with open("/tmp/downloaded_content.html", 'wb') as f:
                f.write(pdf_data)
            print("📄 Saved downloaded content to /tmp/downloaded_content.html for debugging")
            
            # Try one more time with a simple GET request using all cookies
            print("🔄 Final attempt with simple requests...")
            import requests
            
            session = requests.Session()
            for cookie in driver.get_cookies():
                session.cookies.set(cookie['name'], cookie['value'])
            
            # Add referer header
            session.headers['Referer'] = driver.current_url
            
            response = session.get(pdf_url, stream=True)
            if response.status_code == 200:
                pdf_data = response.content
                if pdf_data.startswith(b'%PDF'):
                    print("✅ Final attempt successful!")
                else:
                    print("❌ Final attempt also returned non-PDF content")
                    return None
        
        return pdf_data
        
    except Exception as e:
        print(f"❌ Error during login or download: {str(e)}")
        print(f"Full traceback: {traceback.format_exc()}")
        if driver:
            try:
                driver.save_screenshot("/tmp/error_screenshot.png")
                print("📸 Error screenshot saved")
            except:
                pass
        return None
    finally:
        if driver:
            try:
                driver.quit()
                print("🔚 Chrome driver closed")
            except:
                pass

def send_email(email_to, email_from, email_pass, pdf_data, username):
    """Send email with paystub attachment"""
    try:
        # Save PDF temporarily
        temp_file = f"/tmp/paystub_{username}_{int(time.time())}.pdf"
        with open(temp_file, 'wb') as f:
            f.write(pdf_data)
        
        # Send email
        yag = yagmail.SMTP(email_from, email_pass)
        yag.send(
            to=email_to,
            subject="🧾 Weekly Paystub",
            contents="Here is your newest paystub.",
            attachments=temp_file
        )
        print(f"✅ Email sent to {email_to}")
        
        # Clean up
        os.remove(temp_file)
        return True
        
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return False

def save_to_s3(pdf_data, username, bucket_name=None):
    """Optionally save paystub to S3 for archival"""
    if not bucket_name:
        return
    
    try:
        s3 = boto3.client('s3', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
        key = f"paystubs/{username}/{username}_{int(time.time())}.pdf"
        s3.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=pdf_data,
            ContentType='application/pdf'
        )
        print(f"📦 Saved to S3: s3://{bucket_name}/{key}")
    except Exception as e:
        print(f"❌ Failed to save to S3: {e}")

def process_user(user_config):
    """Process a single user's paystub download and email"""
    username = user_config.get('username')
    password = user_config.get('password')
    email_to = user_config.get('email_to')
    email_from = user_config.get('email_from')
    email_pass = user_config.get('email_pass')
    s3_bucket = user_config.get('s3_bucket')
    
    # Validate config
    if not all([username, password, email_to, email_from, email_pass]):
        print(f"⚠️ Missing required configuration for user")
        missing = []
        if not username: missing.append("username")
        if not password: missing.append("password")
        if not email_to: missing.append("email_to")
        if not email_from: missing.append("email_from")
        if not email_pass: missing.append("email_pass")
        print(f"Missing fields: {', '.join(missing)}")
        return False
    
    # Download paystub
    pdf_data = login_and_download(username, password)
    if not pdf_data:
        return False
    
    # Save to S3 if configured
    if s3_bucket:
        save_to_s3(pdf_data, username, s3_bucket)
    
    # Send email
    return send_email(email_to, email_from, email_pass, pdf_data, username)

def lambda_handler(event, context):
    """Lambda handler function"""
    print("🚀 Starting paystub download process...")
    print(f"Environment: AWS_REGION={os.environ.get('AWS_REGION')}")
    print(f"Event: {json.dumps(event, indent=2)}")
    
    # Test Chrome installation
    try:
        chrome_version = os.popen('/opt/chrome/chrome --version').read().strip()
        print(f"Chrome version: {chrome_version}")
    except:
        print("❌ Could not get Chrome version")
    
    try:
        chromedriver_version = os.popen('/opt/chromedriver --version').read().strip()
        print(f"ChromeDriver version: {chromedriver_version}")
    except:
        print("❌ Could not get ChromeDriver version")
    





    # Get users configuration from event or SSM Parameter Store
    users = []

    try:
        users_json = os.environ.get("USERS_JSON", "[]")
        users = json.loads(users_json)
        print(f"📋 Loaded {len(users)} users from environment")
    except Exception as e:
        print(f"❌ Failed to load USERS_JSON: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps('Invalid USERS_JSON')
        }

    if not users:
        print("❌ No users configured")
        return {
            'statusCode': 400,
            'body': json.dumps('No users configured')
        }




    # Process each user
    results = []
    for i, user_config in enumerate(users):
        print(f"\n{'='*50}")
        print(f"Processing user {i+1} of {len(users)}")
        print(f"{'='*50}")
        
        try:
            # If passwords are stored in SSM, retrieve them
            if 'password_param' in user_config:
                user_config['password'] = get_parameter(user_config['password_param'])
            if 'email_pass_param' in user_config:
                user_config['email_pass'] = get_parameter(user_config['email_pass_param'])
            
            success = process_user(user_config)
            results.append({
                'username': user_config.get('username'),
                'success': success
            })
        except Exception as e:
            print(f"❌ Error processing user: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            results.append({
                'username': user_config.get('username', 'unknown'),
                'success': False,
                'error': str(e)
            })
    
    print("\n✅ Process complete")
    print(f"Results: {json.dumps(results, indent=2)}")
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Paystub process complete',
            'results': results
        })
    }