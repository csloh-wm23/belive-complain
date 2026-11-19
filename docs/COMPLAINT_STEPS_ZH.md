# 投诉处理：日常使用步骤

## 顾客提交与追踪

1. 打开 Make a complaint，填写物业名称、问题标题和详情。房号和邮箱可选，无需验证租客身份。
2. 提交后可保存 BL 编号，方便日后联系员工。
3. Hermes 能处理的一般问题会直接回复；需要维修、调查或员工决定的案件进入 Needs staff。
4. 日后使用提交投诉时的浏览器打开 Track complaint，即可查看回复和继续留言。

## 员工处理

1. 在 Complaints → Needs staff 打开案件，阅读 Conversation 和 Next step。
2. 点 Take ownership，案件进入 Staff handling。
3. 在 Reply 填写或修改给顾客的回复，勾选 I reviewed this reply，点 Send reply。系统会同时保存并发送，不用先另存草稿。
4. 实际处理完成后，在 Internal note / work completed 记录所做的工作（至少 8 个字符），点 Mark handled · ask customer to confirm。案件进入 Follow-up。
5. 顾客在原来的浏览器打开 Track complaint，点 Issue resolved；若仍有问题，填写详情并点 Still unresolved。
6. 顾客确认解决后，员工刷新案件，在内部记录里写明结果与依据，勾选已核查确认和证据，点 Close complaint，完成结案。
7. 若顾客点 Still unresolved，案件回到 Needs staff，重新接手处理；即使已结案，也可以重新打开。

公开评论则由员工先接手，再于 Case progress 记录并核查处理结果，然后选择 Close complaint。

## Follow-up 时要做什么

Follow-up 表示等待顾客确认。正常结案需要顾客确认；如果顾客 7 天内没有回复，系统会自动记录为“未回复结案”，不表示问题已解决。

顾客在等待期间继续留言时，案件回到 Staff handling，停止等待计时。员工处理后再次点 Mark handled，才开始新一轮等待。内部备注和系统提醒不会重置等待时间；员工在等待期间发送新回复会重新计算等待时间。

自动结案后，顾客仍可在原来的浏览器打开投诉，发送留言或点 Still unresolved，案件即回到 Needs staff。无需重新投诉。

等待天数可在 System setup → AI & knowledge → Staff routing → Close after no customer reply 修改，默认 7 天。系统运行期间定期检查；关机或关闭服务时不执行，重新启动后会补查。未完成工单、员工仍在处理的案件、以及顾客已确认等待员工核查的案件，不会因未回复自动关闭。

## 内部备注和少用操作

Internal note / work completed 是员工内部记录，顾客看不到；要通知顾客，请用 Reply → Send reply。

More options 里保留内部备注、下一步与截止时间、分类和优先级修改，以及主动退回 Needs staff。它们使用上方的内部记录内容。一般处理不需要打开这里。

日常案件界面已移除验证租客关联、新建工单和外部发送队列按钮。旧案件若仍有未完成工单，会保留完成入口，避免无法结案。

## 结案后教 Hermes

在员工核实关闭的案件中，使用 Teach future replies 填写可复用的顾客回复和适用的一般问题，确认不含私人信息后保存经验。只有审阅通过且开启公开复用的经验才用于公开自动回复；员工结案本身不会自动批准公开经验。因未回复而自动关闭的案件没有核实结果，不能直接作为 self-learning 经验。

## 测试范围

`tests/browser_complaint_flow.py` 使用独立临时数据库和模拟 AI，通过正式投诉页面测试无租客验证提交、同一浏览器追踪、员工回复、内部记录隔离、顾客确认、结案与重新打开，并检查桌面和手机宽度。此项测试不验证真实模型或外部平台授权。
