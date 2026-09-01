"""Ansible Playbook 模板"""
PLAYBOOK_TEMPLATES = {
    "ping": {
        "name": "设备连通性检查",
        "description": "Ping 测试设备连通性",
        "template": """---
- name: 设备连通性检查
  hosts: all
  gather_facts: no
  tasks:
    - name: Ping 设备
      ping:
      register: ping_result
    - name: 显示结果
      debug:
        msg: "{{ inventory_hostname }}: {{ '成功' if ping_result.ping == 'pong' else '失败' }}"
""",
    },
    "backup_config": {
        "name": "备份设备配置",
        "description": "备份设备运行配置到本地",
        "template": """---
- name: 备份设备配置
  hosts: all
  gather_facts: no
  tasks:
    - name: 获取配置
      {{ module }}:
      register: config_result
    - name: 保存配置
      copy:
        content: "{{ config_result.stdout }}"
        dest: "{{ backup_dir }}/{{ inventory_hostname }}_{{ ansible_date_time.date }}.cfg"
      when: config_result is succeeded
""",
    },
    "get_facts": {
        "name": "获取设备信息",
        "description": "获取设备基本信息",
        "template": """---
- name: 获取设备信息
  hosts: all
  gather_facts: yes
  tasks:
    - name: 显示设备信息
      debug:
        msg: "{{ inventory_hostname }}: {{ ansible_net_hostname }} ({{ ansible_net_model }})"
""",
    },
}


def render_playbook(template_name: str, variables=None):
    template_info = PLAYBOOK_TEMPLATES.get(template_name)
    if not template_info:
        raise ValueError(f"模板 '{template_name}' 不存在")
    content = template_info["template"]
    if variables:
        for key, value in variables.items():
            content = content.replace(f"{{{{ {key} }}}}", str(value))
    return content
