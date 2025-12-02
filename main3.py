import streamlit as st
from supabase import create_client
from datetime import datetime, date, timedelta
import pandas as pd
import math
import time
import yagmail
import random
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 从环境变量获取敏感信息
app_password = os.getenv("GMAIL_APP_PASSWORD", "")
url = os.getenv("SUPABASE_URL", "")
key = os.getenv("SUPABASE_KEY", "")
environment = os.getenv("ENVIRONMENT", "development")

# 查询日期的可用时间
def available(av_date):
    try:
        if av_date in st.session_state.special_time:
            return st.session_state.special_time[av_date]
        else:
            return st.session_state.week_time["hours"][av_date.weekday()]
    except Exception:
        return False

# 发送密码 - 安全版本
def send_random_password(srp_email):
    # 生成随机密码
    cod = "".join(str(random.randint(0, 9)) for _ in range(4))
    
    # 在云端部署时，不发送真实邮件（安全考虑）
    if environment == "production":
        # 在生产环境，只显示密码，不发送邮件
        st.info(f"For security, email sending is disabled in production. Your password is: {cod}")
        return cod
    
    # 在开发环境尝试发送邮件
    try:
        if app_password:
            yag = yagmail.SMTP("forttrof333@gmail.com", app_password)
            yag.send(
                to=srp_email,
                subject="Your Password of MyTimeManagement",
                contents=f"You have signed in successfully! Your Password is {cod}.")
            return cod
        else:
            st.info(f"Email sending not configured. Your password is: {cod}")
            return cod
    except Exception as e:
        st.warning(f"Email sending failed. Your password is: {cod}")
        return cod

# 生成日程
def generate_sch():
    # 将completed_time存到saved_completed_time
    gen_task_response = supabase.table("pp_task").select("*").execute()
    gen_task_rows = gen_task_response.data
    for row in gen_task_rows:
        if row["email"] == st.session_state.login_email:
            gen_completed_time = row["completed_time"]
            gen_saved_completed_time = row["saved_completed_time"]
            response = supabase.table("pp_task") \
                .update({
                "completed_time": 0,
                "saved_completed_time": gen_completed_time + gen_saved_completed_time
            }) \
                .eq("id", row["id"]) \
                .execute()
            st.session_state.user_task_info[row["task"]][3] = 0
            st.session_state.user_task_info[row["task"]][4] = gen_completed_time + gen_saved_completed_time

    # 创建最早日期和最后日期之间所有日期的字典+详细日期的信息
    gen_min_date = datetime.strptime(min(st.session_state.user_task_table["start date"]), "%Y-%m-%d").date()
    gen_max_date = datetime.strptime(max(st.session_state.user_task_table["due date"]), "%Y-%m-%d").date()
    
    gen_date = {}
    schedule_info = {}
    
    # 修复无限循环问题
    current_date = gen_min_date
    while current_date <= gen_max_date:
        if current_date >= date.today():  # 只处理今天及之后的日期
            gen_date_task = []
            for task in st.session_state.user_task_info:
                task_start = datetime.strptime(st.session_state.user_task_info[task][0], "%Y-%m-%d").date()
                task_due = datetime.strptime(st.session_state.user_task_info[task][1], "%Y-%m-%d").date()
                if task_start <= current_date <= task_due:
                    gen_date_task.append(task)
            gen_date[current_date] = [available(current_date), gen_date_task]
            schedule_info[current_date] = []
        current_date += timedelta(days=1)

    # 获取每个task持续日期的所有可用小时数
    task_hour_available = {}
    for task in st.session_state.user_task:
        task_hour_available[task] = 0
    
    gen_date_change = gen_date.copy()
    for task in st.session_state.user_task:
        for gen_date_key in gen_date_change:
            if task in gen_date_change[gen_date_key][1]:
                task_hour_available[task] += gen_date_change[gen_date_key][0]
    
    # 获取每个task每小时平均学习时长，并从大到小排列
    task_hour_average = {}
    for task in st.session_state.user_task_info:
        remaining_time = st.session_state.user_task_info[task][2] - st.session_state.user_task_info[task][4]
        if task_hour_available[task] > 0:
            task_hour_average[task] = remaining_time / task_hour_available[task]
        else:
            task_hour_average[task] = 0
    
    task_hour_average = dict(sorted(task_hour_average.items(), key=lambda x: x[1], reverse=True))

    # 初始化任务总时间记录
    task_total = {}
    for task in st.session_state.user_task_info:
        task_total[task] = 0

    # 从平均时长最高的开始，设计schedule
    for task_key in task_hour_average:
        # 重新计算task_hour_available
        task_hour_available = {}
        for task in st.session_state.user_task:
            task_hour_available[task] = 0
        for task in st.session_state.user_task:
            for gen_date_key in gen_date_change:
                if task in gen_date_change[gen_date_key][1]:
                    task_hour_available[task] += gen_date_change[gen_date_key][0]

        for gen_date_key in gen_date_change:
            if task_key in gen_date_change[gen_date_key][1] and task_hour_available[task_key] > 0:
                remaining_time = st.session_state.user_task_info[task_key][2] - st.session_state.user_task_info[task_key][4]
                if remaining_time <= 0:
                    continue
                    
                # 计算每天分配的时间
                daily_hours = gen_date_change[gen_date_key][0]
                proportion = daily_hours / task_hour_available[task_key] if task_hour_available[task_key] > 0 else 0
                working_minutes = remaining_time * proportion
                
                # 确保分配的时间不超过当天可用时间
                available_minutes = daily_hours * 60
                if working_minutes > available_minutes:
                    working_minutes = available_minutes
                
                if working_minutes > 0:
                    # 更新当天剩余可用时间
                    gen_date_change[gen_date_key][0] -= working_minutes / 60
                    if gen_date_change[gen_date_key][0] < 0:
                        gen_date_change[gen_date_key][0] = 0
                    
                    # 记录分配的时间
                    task_total[task_key] += working_minutes
                    schedule_info[gen_date_key].append([task_key, [math.ceil(working_minutes), round(working_minutes, 2)]])

    # 上传至数据库
    response = supabase.table("pp_sch") \
        .delete() \
        .eq("email", st.session_state.login_email) \
        .execute()
    
    for date_key in schedule_info:
        for task_info in schedule_info[date_key]:
            if task_info[1][1] <= 0:
                continue
            response = supabase.table("pp_sch").insert({
                "email": st.session_state.login_email,
                "date": date_key.isoformat(),
                "task": task_info[0],
                "time": task_info[1][1],
                "completion": False
            }).execute()

# 从pp_password数据库获取信息
if url and key:
    supabase = create_client(url, key)
else:
    st.warning("Database connection not configured. Some features may not work.")
    supabase = None

user_password = {}
if supabase:
    try:
        password_response = supabase.table("pp_password").select("*").execute()
        password_rows = password_response.data
        for row in password_rows:
            user_password[row["email"]] = row["password"]
    except Exception as e:
        st.warning(f"Could not connect to database: {str(e)}")

def login(login_email, login_password):
    if login_email in user_password and user_password[login_email] == login_password:
        return True
    else:
        return False

# login_bool,布尔值,True=已登入,False=未登入
if "login_bool" not in st.session_state:
    st.session_state.login_bool = False
# login_email,字符串,没登入时是空字符串，登入了话字符串存了邮箱
if "login_email" not in st.session_state:
    st.session_state.login_email = ""
# after_rerun,默认为空字符串
if "after_rerun" not in st.session_state:
    st.session_state.after_rerun = ""

if st.session_state.after_rerun != "":
    st.toast(st.session_state.after_rerun)
    st.session_state.after_rerun = ""

# 登入dialog
@st.dialog("log in")
def dialog_login():
    dialog_login_email = st.text_input("email")
    dialog_login_password = st.text_input("password", type="password")
    if st.button("log in", key="login_1"):
        if login(dialog_login_email, dialog_login_password):
            st.session_state.login_bool = True
            st.session_state.login_email = dialog_login_email
            st.session_state.after_rerun = "you are logged in"
            st.rerun()
        else:
            st.error("login failed")

# 注册dialog - 安全版本
@st.dialog("sign in")
def dialog_signin():
    # 在生产环境显示警告
    if environment == "production":
        st.warning("Sign up is currently disabled in production mode.")
        st.info("Please contact the administrator for access.")
        return
    
    dialog_signin_email = st.text_input("email")
    if st.button("sign in", key="112223signin"):
        if dialog_signin_email in user_password:
            st.error("email already exist")
        else:
            try:
                dialog_password = send_random_password(dialog_signin_email)
                if supabase:
                    response = supabase.table("pp_password").insert({"password": dialog_password, "email": dialog_signin_email}).execute()
                    st.session_state.after_rerun = "you have signed in successfully! Your password has been generated."
                    st.rerun()
                else:
                    st.error("Database not available")
            except Exception as e:
                st.error(f"Error: {str(e)}")

# 登入sidebar
with st.sidebar:
    st.title("MyTimeManagement")
    if not st.session_state.login_bool:
        if st.button("log in", key="login_2"):
            dialog_login()
        if st.button("sign in"):
            dialog_signin()
    if st.session_state.login_bool:
        if st.button("log out"):
            st.session_state.login_bool = False
            st.session_state.login_email = ""
            st.session_state.after_rerun = "you are logged out"
            st.rerun()
    if st.session_state.login_bool:
        st.success(f"account: {st.session_state.login_email}")
    else:
        st.error("you are not logged in")

    if st.button("rerun"):
        st.session_state.after_rerun = "rerun successfully"
        st.rerun()

# 两个tab
scheduler, timer, fortest = st.tabs(["scheduler", "timer", "开发"])

# 更改数据库pp_task的completed_time
if "task_completion_dic" not in st.session_state:
    st.session_state.task_completion_dic = {}

def completed_time_update():
    for task_completion_key in st.session_state.task_completion_dic:
        if st.session_state.task_completion_dic[task_completion_key]:
            response = supabase.table("pp_sch") \
                .update({"completion": True}) \
                .eq("id", task_completion_key) \
                .execute()
        else:
            response = supabase.table("pp_sch") \
                .update({"completion": False}) \
                .eq("id", task_completion_key) \
                .execute()

if supabase:
    completed_time_update()

    # 根据task完成数据更改pp_task的completed_time
    task_response = supabase.table("pp_task").select("*").execute()
    task_rows_ini = task_response.data

    st.session_state.task_completed_time = {}
    for row in task_rows_ini:
        if row["email"] == st.session_state.login_email:
            st.session_state.task_completed_time[row["task"]] = 0

    sch_response = supabase.table("pp_sch").select("*").execute()
    sch_rows = sch_response.data
    for row in sch_rows:
        if row["email"] == st.session_state.login_email and row["completion"]:
            st.session_state.task_completed_time[row["task"]] += row["time"]
    for task_key in st.session_state.task_completed_time:
        st.session_state.task_completed_time[task_key] = round(st.session_state.task_completed_time[task_key], 2)

    for row in task_rows_ini:
        if row["email"] == st.session_state.login_email:
            response = supabase.table("pp_task") \
                .update({"completed_time": st.session_state.task_completed_time[row["task"]]}) \
                .eq("id", row["id"]) \
                .execute()

    # 获取数据库pp_task的数据
    task_response = supabase.table("pp_task").select("*").execute()
    task_rows = task_response.data
else:
    task_rows = []

st.session_state.user_task = []
st.session_state.user_task_info = {}
st.session_state.user_task_table = {"task": [], "start date": [], "due date": [], "total time": [], "completed": [],
                                    "progress": [], "days left": []}

for row in task_rows:
    if row["email"] == st.session_state.login_email and row["task"] not in st.session_state.user_task:
        st.session_state.user_task.append(row["task"])
        st.session_state.user_task_info[row["task"]] = [row["start_date"], row["due_date"], row["total_time"],
                                                        row["completed_time"], row["saved_completed_time"]]
        st.session_state.user_task_table["task"].append(row["task"])
        st.session_state.user_task_table["start date"].append(row["start_date"])
        st.session_state.user_task_table["due date"].append(row["due_date"])
        st.session_state.user_task_table["total time"].append(f"{row['total_time']} minutes")
        st.session_state.user_task_table["completed"].append(
            f"{math.ceil(row['completed_time'] + row['saved_completed_time'])} minutes")
        st.session_state.user_task_table["progress"].append(
            f"{int((row['completed_time'] + row['saved_completed_time']) / row['total_time'] * 100 if row['total_time'] > 0 else 0)}%")
        st.session_state.user_task_table["days left"].append(
            f"{(datetime.strptime(row['due_date'], '%Y-%m-%d').date() - date.today()).days} days")

# 第一个tab用的,新增task
@st.dialog("insert task")
def insert_task():
    if not supabase:
        st.error("Database not available")
        return
        
    it_task_title = st.text_input("task title")
    it_start_date = st.date_input("start date")
    it_due_date = st.date_input("due date")
    it_minutes = st.toggle("input in minutes")
    if it_minutes:
        it_total_time = st.number_input("total working time (minutes)", step=1, format="%d")
    else:
        it_total_time = st.number_input("total working time (hours)", step=1, format="%d") * 60
    if st.button("submit"):
        if it_task_title == "":
            st.error("task title can't be empty")
        elif it_start_date == it_due_date:
            st.error("task start and due date can't be the same")
        elif it_start_date > it_due_date:
            st.error("task can't start before the due date")
        elif it_total_time == 0:
            st.error("total working time can't be zero")
        else:
            st.session_state.after_rerun = "task inserted"
            supabase.table("pp_task").insert({
                "email": st.session_state.login_email,
                "task": it_task_title,
                "start_date": it_start_date.isoformat(),
                "due_date": it_due_date.isoformat(),
                "total_time": it_total_time,
                "completed_time": 0,
                "saved_completed_time": 0
            }).execute()
            st.rerun()

@st.dialog("remove task")
def remove_task():
    if not supabase:
        st.error("Database not available")
        return
        
    remove_which_task = st.selectbox("remove task", st.session_state.user_task)
    if st.button("remove"):
        response = supabase.table("pp_task") \
            .delete() \
            .eq("task", remove_which_task) \
            .eq("email", st.session_state.login_email) \
            .execute()
        st.session_state.after_rerun = "task removed"
        st.rerun()

# 从数据库获取每周的小时数
hours = [0, 0, 0, 0, 0, 0, 0]
if st.session_state.login_bool and supabase:
    # 如果数据库找不到email,新建一个row
    hour_insert_new = supabase.table("pp_hour") \
        .select("email") \
        .eq("email", st.session_state.login_email) \
        .execute()
    hour_insert_new = len(hour_insert_new.data) > 0
    if not hour_insert_new:
        try:
            response = supabase.table("pp_hour").insert({
                "email": st.session_state.login_email,
                "0": 3,
                "1": 3,
                "2": 3,
                "3": 3,
                "4": 3,
                "5": 3,
                "6": 3
            }).execute()
            st.rerun()
        except Exception as e:
            st.warning(f"Could not create hour record: {str(e)}")
    # 从数据库获取信息
    try:
        hour_response = supabase.table("pp_hour").select("*").execute()
        hour_rows = hour_response.data
        for row in hour_rows:
            if row["email"] == st.session_state.login_email:
                hours = [row["0"], row["1"], row["2"], row["3"], row["4"], row["5"], row["6"]]
    except Exception as e:
        st.warning(f"Could not fetch hour data: {str(e)}")

WEEK_DAY = {0: "monday", 1: "tuesday", 2: "wednesday", 3: "thursday", 4: "friday", 5: "saturday", 6: "sunday"}

st.session_state.week_time = {"day": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
                              "hours": hours}
if "special_time" not in st.session_state:
    st.session_state.special_time = {}

# 将数据库获取特殊情况
if supabase:
    try:
        event_response = supabase.table("pp_event").select("*").execute()
        event_rows = event_response.data
        for row in event_rows:
            if row["email"] == st.session_state.login_email:
                st.session_state.special_time[datetime.strptime(row["date"], "%Y-%m-%d").date()] = row["hour"]
    except Exception as e:
        st.warning(f"Could not fetch event data: {str(e)}")

st.session_state.special_time_table = {"date": [], "hours": []}
for date_key in st.session_state.special_time:
    st.session_state.special_time_table["date"].append(f"{date_key} ({WEEK_DAY[date_key.weekday()]})")
    st.session_state.special_time_table["hours"].append(str(st.session_state.special_time[date_key]))

# 添加时间特例dialog
@st.dialog("insert event")
def insert_event():
    if not supabase:
        st.error("Database not available")
        return
        
    ie_date = st.date_input("date", key="insert event")
    ie_hour = st.number_input("hour", step=1, key="insert event2")
    if st.button("submit", key="insert event3"):
        if ie_date < date.today():
            st.error("can only insert future event")
        elif ie_date in st.session_state.special_time:
            st.error("can't insert repeated event")
        else:
            st.session_state.special_time[ie_date] = ie_hour
            st.session_state.after_rerun = "event inserted"
            response = supabase.table("pp_event").insert({
                "email": st.session_state.login_email,
                "date": ie_date.isoformat(),
                "hour": ie_hour
            }).execute()
            st.rerun()

# 删除时间特例dialog
@st.dialog("disable event")
def disable_event():
    if not supabase:
        st.error("Database not available")
        return
        
    de_date = st.date_input("date", key="disable event1")
    if st.button("submit", key="disable event2"):
        if de_date in st.session_state.special_time:
            del st.session_state.special_time[de_date]
            st.session_state.after_rerun = "event disabled"
            supabase.table("pp_event").delete().eq("email", st.session_state.login_email).eq("date", de_date.isoformat()).execute()
            st.rerun()
        else:
            st.error("no need to disable unexist event")

# 第一个tab
with scheduler:
    if not st.session_state.login_bool:
        st.error("please log in")
    else:
        if not supabase:
            st.warning("Database not connected. Some features may not work.")
        
        insert_task_col, abcd, update_table = st.columns([1, 3, 1])
        with insert_task_col:
            if st.button("insert task"):
                insert_task()
        with update_table:
            if st.button("update info"):
                st.session_state.after_rerun = "table updated"
                st.rerun()
        with abcd:
            if st.button("remove task"):
                remove_task()

    # hour表格
    if st.session_state.user_task_table["task"]:
        user_task_table_pd = pd.DataFrame(st.session_state.user_task_table)
        st.data_editor(
            user_task_table_pd,
            hide_index=True,
            use_container_width=True,
            disabled=True,
            column_config={
                "task": st.column_config.TextColumn("task", width="medium"),
            }
        )
    else:
        st.dataframe(st.session_state.user_task_table)

    week1, week2 = st.columns(2)
    with week1:  # 每周小时数
        st.session_state.week_time = st.data_editor(st.session_state.week_time, disabled=["day"])
        if supabase and st.session_state.week_time["hours"] != hours:
            try:
                response = supabase.table("pp_hour") \
                    .update({
                    "0": st.session_state.week_time["hours"][0],
                    "1": st.session_state.week_time["hours"][1],
                    "2": st.session_state.week_time["hours"][2],
                    "3": st.session_state.week_time["hours"][3],
                    "4": st.session_state.week_time["hours"][4],
                    "5": st.session_state.week_time["hours"][5],
                    "6": st.session_state.week_time["hours"][6],
                }) \
                    .eq("email", st.session_state.login_email) \
                    .execute()
                st.session_state.after_rerun = "week hour updated"
                st.rerun()
            except Exception as e:
                st.error(f"Could not update hour data: {str(e)}")
    with week2:  # 特殊情况
        week21, week22 = st.columns(2)
        with week21:
            if st.button("insert special case"):
                insert_event()
        with week22:
            if st.button("disable special case"):
                disable_event()
        st.dataframe(st.session_state.special_time_table)

    st.session_state.schedule_info = {}
    if supabase:
        try:
            sch_response = supabase.table("pp_sch").select("*").execute()
            sch_rows = sch_response.data
            for row in sch_rows:
                if row["email"] != st.session_state.login_email:
                    continue
                st.session_state.schedule_info[(row["id"], row["date"])] = [row["task"], [math.ceil(row["time"]), row["time"]]]
        except Exception as e:
            st.warning(f"Could not fetch schedule data: {str(e)}")

    # 选择查看日期
    display_working_hour = 0
    display_task = []
    display_day1, display_day2 = st.columns(2)
    if "display_date" not in st.session_state:
        st.session_state.display_date = date.today()
    with display_day1:
        st.session_state.display_date = st.date_input("date")
    
    for date_key in st.session_state.schedule_info:
        if str(st.session_state.display_date) in date_key:
            display_task.append([f"{st.session_state.schedule_info[date_key][0]}, {st.session_state.schedule_info[date_key][1][0]} minutes", date_key[0]])
            display_working_hour += st.session_state.schedule_info[date_key][1][0]
    
    with display_day2:
        st.text(f"{st.session_state.display_date} ({WEEK_DAY[st.session_state.display_date.weekday()]})\navailable time: {available(st.session_state.display_date)} hours\nworking time: {display_working_hour} minutes")

    for task in display_task:
        if supabase:
            try:
                response = supabase.table("pp_sch") \
                    .select("completion") \
                    .eq("id", task[1]) \
                    .limit(1) \
                    .execute()
                if response.data:
                    complete_value = response.data[0]["completion"]
                else:
                    complete_value = False
            except:
                complete_value = False
        else:
            complete_value = False
            
        st.session_state.task_completion_dic[task[1]] = st.toggle(task[0], key=task[1], value=complete_value)

    col_generate, col_text_gen = st.columns([1, 3])
    with col_generate:
        if st.button("generate schedule") and st.session_state.login_bool:
            if not supabase:
                st.error("Database not available")
            else:
                completed_time_update()
                try:
                    generate_sch()
                    st.session_state.after_rerun = "schedule generated"
                    st.rerun()
                except ZeroDivisionError:
                    st.error("please check your setting")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
    with col_text_gen:
        st.text("You schedule will always be saved, there is no need to generate new schedule if you havn't make any changes")

with fortest:
    st.text("st.session_state.user_task:")
    st.text(st.session_state.user_task)
    st.text("st.session_state.user_task_info:")
    st.text(st.session_state.user_task_info)
    st.text("st.session_state.user_task_table:")
    st.text(st.session_state.user_task_table)
    st.text("st.session_state.week_time:")
    st.text(st.session_state.week_time)
    st.text("st.session_state.special_time:")
    st.text(st.session_state.special_time)

def clock(clock_int):
    min = clock_int // 60
    sec = clock_int % 60
    return f"{'0' * (2 - len(str(min)))}{min}:{'0' * (2 - len(str(sec)))}{sec}"

def pomodoro_timer():
    # 初始化Pomodoro计时器的session state
    if "pomodoro_running" not in st.session_state:
        st.session_state.pomodoro_running = False
    if "pomodoro_end_time" not in st.session_state:
        st.session_state.pomodoro_end_time = None
    if "pomodoro_phase" not in st.session_state:
        st.session_state.pomodoro_phase = "work"
    if "pomodoro_cycle" not in st.session_state:
        st.session_state.pomodoro_cycle = 0
    
    # 原始设置的时间
    if "pomodoro_original_study_time" not in st.session_state:
        st.session_state.pomodoro_original_study_time = 25 * 60
    if "pomodoro_original_rest_time" not in st.session_state:
        st.session_state.pomodoro_original_rest_time = 5 * 60
    if "pomodoro_original_long_break_time" not in st.session_state:
        st.session_state.pomodoro_original_long_break_time = 15 * 60
    
    # 用于追踪暂停状态的变量
    if "pomodoro_paused_remaining" not in st.session_state:
        st.session_state.pomodoro_paused_remaining = None
    
    # 用于跟踪阶段切换的变量
    if "pomodoro_last_phase" not in st.session_state:
        st.session_state.pomodoro_last_phase = st.session_state.pomodoro_phase
    if "pomodoro_phase_changed" not in st.session_state:
        st.session_state.pomodoro_phase_changed = False

    # 自定义设置部分
    st.subheader("Timer Settings")
    
    col_input1, col_input2, col_input3 = st.columns(3)
    with col_input1:
        # 学习时间
        study_minutes = st.number_input("Study Time (minutes)", 
                                      value=float(st.session_state.pomodoro_original_study_time / 60),
                                      min_value=1.0, max_value=60.0, step=1.0)
        st.session_state.pomodoro_original_study_time = int(study_minutes * 60)
    
    with col_input2:
        # 休息时间
        rest_minutes = st.number_input("Rest Time (minutes)", 
                                     value=float(st.session_state.pomodoro_original_rest_time / 60),
                                     min_value=1.0, max_value=30.0, step=1.0)
        st.session_state.pomodoro_original_rest_time = int(rest_minutes * 60)
    
    with col_input3:
        # 长休息时间
        long_break_minutes = st.number_input("Long Break Time (minutes)", 
                                           value=float(st.session_state.pomodoro_original_long_break_time / 60),
                                           min_value=5.0, max_value=60.0, step=5.0)
        st.session_state.pomodoro_original_long_break_time = int(long_break_minutes * 60)

    # 格式化时间显示
    def format_time(seconds):
        seconds = int(max(0, seconds))
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins:02d}:{secs:02d}"

    # 计算当前阶段的原始时长
    def get_original_phase_duration():
        if st.session_state.pomodoro_phase == "work":
            return st.session_state.pomodoro_original_study_time
        elif st.session_state.pomodoro_phase == "short_break":
            return st.session_state.pomodoro_original_rest_time
        else:
            return st.session_state.pomodoro_original_long_break_time

    # 计算剩余时间的函数
    def calculate_remaining_time():
        if st.session_state.pomodoro_running and st.session_state.pomodoro_end_time:
            # 正在运行：计算到结束时间还有多少秒
            remaining = st.session_state.pomodoro_end_time - time.time()
            return max(0, remaining)
        elif st.session_state.pomodoro_paused_remaining is not None:
            # 暂停状态：返回暂停时保存的剩余时间
            return st.session_state.pomodoro_paused_remaining
        else:
            # 未开始：返回原始时长
            return get_original_phase_duration()

    # 检查阶段是否发生了变化
    def check_phase_change():
        current_phase = st.session_state.pomodoro_phase
        last_phase = st.session_state.pomodoro_last_phase
        
        if current_phase != last_phase:
            st.session_state.pomodoro_last_phase = current_phase
            st.session_state.pomodoro_phase_changed = True
            return True
        return False

    # 检查计时器是否应该结束
    def check_timer_completion():
        if st.session_state.pomodoro_running and st.session_state.pomodoro_end_time:
            current_time = time.time()
            if current_time >= st.session_state.pomodoro_end_time:
                return True
        return False

    # 处理计时器结束的逻辑
    def handle_timer_completion():
        if st.session_state.pomodoro_phase == "work":
            st.session_state.pomodoro_cycle += 1
            
            # 检查是否完成4个周期
            if st.session_state.pomodoro_cycle >= 4:
                st.session_state.pomodoro_phase = "long_break"
                st.session_state.pomodoro_cycle = 0
                next_duration = st.session_state.pomodoro_original_long_break_time
                completion_message = "🎉 Completed 4 cycles! Taking a long break..."
            else:
                st.session_state.pomodoro_phase = "short_break"
                next_duration = st.session_state.pomodoro_original_rest_time
                completion_message = "Work session complete! Taking a short break..."
            
            # 重置暂停剩余时间
            st.session_state.pomodoro_paused_remaining = None
            
            # 开始下一个阶段
            st.session_state.pomodoro_end_time = time.time() + next_duration
            st.session_state.pomodoro_running = True
                
        else:
            # 休息结束，返回工作
            st.session_state.pomodoro_phase = "work"
            next_duration = st.session_state.pomodoro_original_study_time
            st.session_state.pomodoro_end_time = time.time() + next_duration
            st.session_state.pomodoro_running = True
            completion_message = "Break over! Time to work..."
            
            # 重置暂停剩余时间
            st.session_state.pomodoro_paused_remaining = None
        
        # 标记阶段已变化
        st.session_state.pomodoro_phase_changed = True
        
        return completion_message

    # 显示当前计时器状态
    st.subheader("Timer Status")
    
    # 检查阶段是否变化（需要在检查计时器结束之前）
    phase_changed = check_phase_change()
    
    # 检查计时器是否已经结束
    timer_just_ended = False
    completion_message = ""
    
    if check_timer_completion():
        timer_just_ended = True
        completion_message = handle_timer_completion()
        # 立即重新运行以更新显示
        st.rerun()
    
    # 如果阶段变化了，也需要刷新
    if phase_changed and st.session_state.pomodoro_phase_changed:
        # 清除标记并刷新
        st.session_state.pomodoro_phase_changed = False
        st.rerun()
    
    # 创建占位符用于动态更新
    timer_placeholder = st.empty()
    progress_placeholder = st.empty()
    status_placeholder = st.empty()
    message_placeholder = st.empty()
    
    # 计算当前剩余时间
    remaining_seconds = calculate_remaining_time()
    original_phase_duration = get_original_phase_duration()
    
    # 显示计时器
    with timer_placeholder.container():
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            # 根据阶段设置颜色
            if st.session_state.pomodoro_phase == "work":
                color_gradient = "linear-gradient(135deg, #ff6b6b 0%, #ee5a52 100%)"  # 红色
            elif st.session_state.pomodoro_phase == "short_break":
                color_gradient = "linear-gradient(135deg, #4cd964 0%, #5ac8fa 100%)"  # 绿色/蓝色
            else:
                color_gradient = "linear-gradient(135deg, #5ac8fa 0%, #007aff 100%)"  # 蓝色
            
            st.markdown(f"""
            <div style="text-align: center; padding: 20px; background: {color_gradient}; 
                        border-radius: 15px; color: white; margin: 10px 0; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <div style="font-size: 18px; margin-bottom: 5px; font-weight: 600;">
                    {st.session_state.pomodoro_phase.replace('_', ' ').upper()}
                </div>
                <div style="font-size: 64px; font-family: 'Courier New', monospace; font-weight: bold; letter-spacing: 2px;">
                    {format_time(remaining_seconds)}
                </div>
                <div style="font-size: 14px; margin-top: 5px; opacity: 0.9;">
                    Cycle: {st.session_state.pomodoro_cycle + 1}/4
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    # 显示进度条 - 使用原始时长计算进度
    if original_phase_duration > 0:
        # 计算相对于原始时长的进度
        if st.session_state.pomodoro_running:
            # 运行时：基于结束时间计算已过时间
            if st.session_state.pomodoro_end_time:
                elapsed = original_phase_duration - (st.session_state.pomodoro_end_time - time.time())
                progress = elapsed / original_phase_duration
            else:
                progress = 0
        else:
            # 暂停或未开始：基于剩余时间计算进度
            elapsed = original_phase_duration - remaining_seconds
            progress = elapsed / original_phase_duration
        
        progress_placeholder.progress(min(max(progress, 0), 1.0))
    
    # 显示状态信息
    with status_placeholder.container():
        col1, col2, col3 = st.columns(3)
        with col1:
            phase_name = st.session_state.pomodoro_phase.replace('_', ' ').title()
            st.metric("Current Phase", phase_name)
        with col2:
            if st.session_state.pomodoro_running:
                st.metric("Status", "Running", delta="▶️")
            else:
                st.metric("Status", "Paused", delta="⏸️")
        with col3:
            remaining_minutes = int(remaining_seconds // 60)
            remaining_secs = int(remaining_seconds % 60)
            st.metric("Time Remaining", f"{remaining_minutes}:{remaining_secs:02d}")

    # 显示消息
    if completion_message:
        with message_placeholder.container():
            st.success(completion_message)
            # 添加一点延迟确保消息显示
            time.sleep(0.1)

    # 控制按钮
    st.subheader("Controls")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        start_disabled = st.session_state.pomodoro_running
        if st.button("▶️ Start", type="primary", use_container_width=True, 
                    disabled=start_disabled, key="start_button"):
            if not st.session_state.pomodoro_running:
                # 获取当前阶段的时长
                if st.session_state.pomodoro_paused_remaining is not None:
                    # 有暂停的剩余时间，使用它
                    duration = st.session_state.pomodoro_paused_remaining
                else:
                    # 没有暂停，使用原始时长
                    if st.session_state.pomodoro_phase == "work":
                        duration = st.session_state.pomodoro_original_study_time
                    elif st.session_state.pomodoro_phase == "short_break":
                        duration = st.session_state.pomodoro_original_rest_time
                    else:
                        duration = st.session_state.pomodoro_original_long_break_time
                
                st.session_state.pomodoro_end_time = time.time() + duration
                st.session_state.pomodoro_running = True
                st.session_state.pomodoro_paused_remaining = None  # 清除暂停状态
                
                st.toast(f"Timer started! {st.session_state.pomodoro_phase.replace('_', ' ')} for {duration//60} min")
                st.rerun()
    
    with col2:
        pause_disabled = not st.session_state.pomodoro_running
        if st.button("⏸️ Pause", use_container_width=True, 
                    disabled=pause_disabled, key="pause_button"):
            if st.session_state.pomodoro_running:
                # 计算剩余时间并保存到暂停状态
                remaining = st.session_state.pomodoro_end_time - time.time()
                if remaining > 0:
                    st.session_state.pomodoro_paused_remaining = remaining
                
                st.session_state.pomodoro_running = False
                st.session_state.pomodoro_end_time = None
                st.toast("Timer paused")
                st.rerun()
    
    with col3:
        if st.button("⏭️ Skip", use_container_width=True, key="skip_button"):
            # 跳过当前阶段
            if st.session_state.pomodoro_phase == "work":
                st.session_state.pomodoro_cycle += 1
                
                if st.session_state.pomodoro_cycle >= 4:
                    st.session_state.pomodoro_phase = "long_break"
                    st.session_state.pomodoro_cycle = 0
                else:
                    st.session_state.pomodoro_phase = "short_break"
            else:
                st.session_state.pomodoro_phase = "work"
            
            # 重置所有状态
            st.session_state.pomodoro_running = False
            st.session_state.pomodoro_end_time = None
            st.session_state.pomodoro_paused_remaining = None
            
            # 标记阶段变化
            st.session_state.pomodoro_phase_changed = True
            
            st.toast(f"Skipped to {st.session_state.pomodoro_phase} phase")
            st.rerun()
    
    with col4:
        if st.button("🔄 Reset", use_container_width=True, key="reset_button"):
            st.session_state.pomodoro_running = False
            st.session_state.pomodoro_phase = "work"
            st.session_state.pomodoro_cycle = 0
            st.session_state.pomodoro_end_time = None
            st.session_state.pomodoro_paused_remaining = None
            
            # 重置时间到默认值
            st.session_state.pomodoro_original_study_time = 25 * 60
            st.session_state.pomodoro_original_rest_time = 5 * 60
            st.session_state.pomodoro_original_long_break_time = 15 * 60
            
            # 重置阶段跟踪
            st.session_state.pomodoro_last_phase = "work"
            st.session_state.pomodoro_phase_changed = True
            
            st.toast("Timer reset to defaults")
            st.rerun()
    
    with col5:
        # 手动刷新按钮
        if st.button("🔄 Refresh", use_container_width=True, key="refresh_button"):
            st.toast("Display refreshed")
            st.rerun()

    # 添加一个隐藏的自动刷新机制，专门用于阶段切换
    if st.session_state.pomodoro_running:
        # 如果计时器正在运行，检查是否应该自动刷新（当阶段变化时）
        if st.session_state.pomodoro_phase_changed:
            # 清除标记
            st.session_state.pomodoro_phase_changed = False
            # 使用一个小的延迟然后刷新
            time.sleep(0.1)
            st.rerun()

    while st.session_state.pomodoro_phase == "work":
        time.sleep(10)
        st.rerun()

# 在timer标签页调用
with timer:
    pomodoro_timer()









