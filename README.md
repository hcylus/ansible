# ansible
通过plugins/inventory/get_host.py动态从esb接口获取cmdb主机信息生成inventory

ssh主机key上传
ansible-playbook authorized_key.yml -e 'hosts=ghoul_adr_cn_gw.*'

生产服更新（进程停启、代码备份更新）
ansible-playbook prod.yml -e 'hosts=ghoul_adr_cn_gw.*'
