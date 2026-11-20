# 投诉处理：日常使用步骤

## 继续员工跟进，而不是立即结案

员工接手后，在 Case progress 写下内部更新，选择 Next follow-up / action deadline（可选），然后点 Continue follow-up。案件会保留在 Follow-up 队列，负责人不变，默认下一次检查时间为 24 小时后。可重复记录更新，也可点 Resume handling 返回 Staff handling。只有核实结果后才点 Close complaint。

这是“员工仍在跟进”，不是“等待顾客回复”：不会触发 7 天未回复自动结案。私人投诉处理完成后，仍可点 Mark handled · ask customer to confirm，重新进入等待顾客确认的流程。

## Google Review 的 AI 回复

Public reply preview 中的内容是 Hermes 生成的草稿，尚未发布。审阅或修改 Reply to copy to the original platform 后，点 Copy public reply，打开原评论，并使用有权管理该商家的 Google Business Profile 账号发布。这里的修改只用于复制，不会覆盖保存的 AI 预览。

已加入 Publish to Google 按钮。连接公司授权后，勾选已审阅并批准公开发送，再点击即可通过官方 API 发布。Google 确认返回后显示 POSTED；失败显示 FAILED，超时不确定显示 UNKNOWN，需要先查看原评论，不会自动重复发布。若已有公司回复，需要另外勾选允许替换。

直接发布需要有权限管理已验证商家的 Google 账号、获批的 Google Business Profile API 项目、带 business.manage 权限的 OAuth access token，以及该账号下的 location 和 review 资源。管理员在 Public reviews 配置获授权的 Google location，并从 API 同步评论；本地 .env 设置 BELIVE_GOOGLE_TOKEN 与 BELIVE_GOOGLE_REPLY_ENABLED=true 后重启。请勿把 token 写进代码或上传 GitHub。

仅导入公开评论链接，不会获得回复权限，也没有 API 所需的 review 资源；这种案件继续使用复制发布，直到从授权的 API 来源导入。内部跟进备注和结案操作不会向 Google 发消息。当前测试使用模拟 Google 返回结果，真实公司授权和实际发布仍待接入。

## 顾客提交与追踪

1. 打开 Make a complaint，填写问题标题和详情。一般问题不用填地点。只有与物业或实体故障有关时，才展开 Add location，按需填写物业、受影响房间或公共区域；公共区域问题不用提供私人房号。邮箱可选，无需验证租客身份。
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

## 用已审核投诉经验进行 Self-learning

### 从不满意的后续回复中改进写作

Self-learning 顶部的 Improve replies from customer feedback 会记录已发布的 Hermes/员工回复及之后的不满意留言。顾客选择 Still unresolved、明确说“没帮助”“重复回答”等都会触发记录；普通道谢或新问题不会直接被认定为失败。

1. 本机运行时会定期检查历史反馈；也可点 Check past replies for feedback。
2. Reply Feedback Learning Agent 在后台分析“原问题 → 发出的回复 → 顾客反馈”，区分沟通问题、仍需员工行动、或原因不清，提出针对性的写作建议。客户继续投诉不是措辞错误的自动证明。
3. 阅读原始证据，修改 Writing improvement tip，勾选审核后点 Approve & use writing tip。Safety Review Agent 检查后才会启用；未审核建议不会影响顾客回复。
4. 点 Test improved reply，Learning Reply Agent 会结合原对话、后续反馈、适用知识和审核建议，生成新草稿与原已发回复对比。此草稿不会自动发给顾客，也不会自动结案。
5. 通过审核的写作建议会提供给后续相关回复。没有适用案件知识的一般问题也可使用相关的反馈写作建议。私人物业来源的建议限制在同一物业，样本来源有明确标签。
6. 页面记录建议提供给多少条已发布回复，以及这些回复后又出现多少次不满意反馈。它们是观察记录，不能证明因果。Reject / revoke tip 会立即停止后续使用；正在生成的测试也不能把被撤回的建议恢复。

这些改进是审核过的经验检索和提示调整，不是自动训练模型权重，也不意味着 Hermes 能替员工完成维修。

1. 打开 Self-learning → Test approved complaint experience，输入实际问题，或从 Approved complaint experience 选择一条已审核经验后换一种问法。
2. 点 Generate first reply。第一轮不提供投诉经验；它仍可按一般客服规则澄清问题。
3. 系统只匹配相关且仍有效的公开审核经验，显示来源案件、适用问题，以及 Sample / test 标签。一般问题不会套用空调、包裹或水压经验。
4. 没有匹配经验时，显示 No relevant approved complaint experience，不填默认写作提示，也不会硬生成“学习后”回答。可先从合适的核实结案中审核添加经验。
5. 有匹配时，阅读来源内容，点 Use this approved experience & generate second reply。第二轮使用同一个问题和该审核经验。被拒绝、重新打开或已修改的经验不能继续用于旧比较。
6. 人工比较相关性和实用性。界面不再按“必须两条编号、一个问号、90 词”声称改善，也不会把同一经验重复存成新经验。之前的格式实验保留在 Legacy demo writing tips 中，并明确标注 SAMPLE。

样本标注来自来源案件的 [TEST]/[SAMPLE]/[DEMO] 标记或已有样本字段；没有这些依据的案件不会被自动宣称为真实顾客数据。

## 测试范围

`tests/browser_complaint_flow.py` 和 `tests/browser_experience_learning.py` 使用独立临时数据库和标注的模拟 AI，通过正式页面测试投诉流程、无需地点的一般问题、按相关性选经验、来源与样本标签，以及桌面和手机宽度。另以本机 qwen3:4b 实际检查一般问题、楼宇规定、公共洗衣机与 Wi-Fi 经验问法。有限场景检查不代表所有回复正确，亦不验证外部平台授权。
