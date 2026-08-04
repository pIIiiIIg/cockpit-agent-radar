#!/usr/bin/env python3
"""2026-08-01..03 高价值论文正文复核结果。"""
import json
import os
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "data", "explanations.json")
ITEMS_PATH = os.path.join(ROOT, "data", "items.json")
NOW = datetime.now(timezone(timedelta(hours=8))).isoformat()


def row(tl, problem, method, workflow, findings, fit, limits, status, code="", model="", note=""):
    return {
        "tl_dr": tl, "problem": problem, "method": method,
        "workflow": workflow, "findings": findings, "project_fit": fit,
        "limitations": limits,
        "open_source": {"status": status, "code_url": code,
                        "model_url": model, "note": note},
        "source_depth": "fulltext", "generated_at": NOW,
        "generated_by": "GPT-5.6 Sol editorial review",
        "review_status": "editorial",
    }


UPDATES = {
    "3832c6eae8": row(
        "M3-DuplexBench 用英日双语、闲聊与多轮问答，在固定历史条件下公平评测全双工模型的轮替和内容。",
        "单轮评测看不到长对话中的上下文漂移；动态对话又会让不同模型获得不同历史，难以公平比较。",
        "从连续双人语音提取SHIFT、PAUSE、BC和BARGE_IN事件，并在无上下文、仅用户历史、完整teacher-forced历史三种条件下评测时序与内容。",
        ["固定相同双人历史", "按事件窗口流式推理", "用时间戳评价轮替并用ASR评价内容"],
        ["覆盖英语和日语、闲聊和多轮QA", "完整历史通常降低轮替延迟，但对不同领域和模型效果不一致"],
        ["可把现有8轮车控压力测试升级为固定完整上下文的多轮基准", "适合检测KV裁剪后指代、跟随指令和时延是否逐轮恶化"],
        ["当前主要适配Moshi式并行双流；Qwen Harness需要编写adapter", "未直接覆盖中文车控工具正确性"],
        "unknown", note="论文正文已核验，尚未确认M3-DuplexBench官方代码发布状态。"),
    "64bb628be2": row(
        "AdaMM把多模态长期记忆拆成语义检索和可执行分析两部分，支持跨时间过滤、聚合与比较。",
        "只做相似度检索会漏掉完整时间范围，无法可靠回答趋势、计数和比较问题。",
        "从对话、图像和时间元数据抽取带来源的属性值，自动归纳重复schema并物化为表；同时保留topic→episode→event检索图，查询规划器组合两类工具。",
        ["提取多模态属性证据", "归纳并演化schema", "物化分析表和语义图", "按查询规划检索/聚合工具"],
        ["在MemEye和MemGallery上分别最高提升约11.3%和7.3%"],
        ["可把乘员偏好、车况和历次车控从纯对话KV迁移到可审计表", "适合回答最近一周常用温度、谁经常调哪个座位等分析问题"],
        ["需要持续可靠地做实体归一和属性抽取", "与实时话轮控制不是同一层能力"],
        "unknown", note="论文已公开；官方实现链接需进一步核验。"),
    "c90d454b37": row(
        "Mage-VL利用视频编码器已有的I/P帧、运动向量和残差，只编码真正变化的区域，实现主动式流视频理解。",
        "均匀抽帧和密集patch会让持续视频流token爆炸，简单场景也消耗大量算力。",
        "Mage-ViT保留完整I帧，仅保留P帧中编码器花费比特的动态patch；轻量System 1事件闸门决定何时唤醒Qwen3-4B System 2推理。",
        ["读取H.264/HEVC或神经codec信息", "筛选运动/高熵patch", "事件闸门触发", "因果解码器推理"],
        ["视觉token减少超过75%", "相对均匀抽帧最高3.5倍墙钟加速", "4B模型静态任务接近Qwen3-VL-4B"],
        ["可作为座舱摄像头流的视觉前端，只有乘员动作或场景变化时写KV", "与音频VAD对应，可形成视觉事件门"],
        ["目前是视觉/视频理解模型，不是完整语音全双工助手", "依赖codec元数据和对应处理器"],
        "open", "https://github.com/microsoft/Mage",
        "https://huggingface.co/microsoft/Mage-VL",
        "代码、模型和流式gate已公开。"),
    "f0237f934e": row(
        "faster-enhancer.c把FastEnhancer-Medium固化成无依赖C/int8流式运行时，可在普通CPU持续降噪。",
        "常开麦克风的增强模型不能只看离线RTF，还要满足每6.67ms deadline、功耗和无动态分配。",
        "固定模型专用int8 GEMM、Winograd卷积、fp16跨阶段状态、融合GRU与反量化；启动后零堆分配，按CPU ISA选择实现。",
        ["每次输入320个48k采样", "因果增强且无look-ahead", "SIMD int8执行", "输出同长度PCM"],
        ["Apple M2 RTF 0.069，较fp32 ONNX快3.3倍", "Galaxy S23+ RTF 0.096", "PESQ仅比fp32低0.006"],
        ["可作为AEC之后、VAD/Qwen之前的端侧NS候选", "适合车机CPU常开，减少GPU依赖"],
        ["它做speech enhancement而非扬声器参考驱动的AEC", "48k输入需与当前16k链路重采样"],
        "open", "https://github.com/kdrkdrkdr/faster-enhancer.c",
        note="C运行时和回归工具公开，复用FastEnhancer权重。"),
    "3bebe83725": row(
        "Voice Memory用可审计memory.md指导冻结的ASR纠错器，并只接受能改善保留集分数的记忆更新。",
        "自由生成式ASR纠错会过度改写正确词，领域词汇又无法靠固定模型持续适配。",
        "Listener读取领域memory决定纠正或保持1-best；异步Thinker对记忆做有限编辑，每次只有严格改善分数才接受。",
        ["ASR生成1-best", "纠错器读取memory并可选择不动作", "离线优化器提出规则", "保留集门控写回memory"],
        ["十域加权WER从8.36%降至7.52%", "ATIS从8.40%降至约3.4%", "过度纠错比例从最高64%降到35%"],
        ["可让车控热词和同音错误通过可审计规则持续学习", "适合记录副驾屏等反复误识别并做回归门控"],
        ["改善主要来自可恢复的领域词，不解决纯声学歧义", "需要可靠保留集避免记忆过拟合"],
        "partial", "https://github.com/huckiyang/voice-memory-notebook",
        note="提供演示和示例代码；完整工程化程度需核验。"),
    "4004e2f714": row(
        "iFLYTEK-Embodied-Omni统一视觉语言、未来视频和动作生成，以共享注意力形成高层脑与低层小脑协作。",
        "VLM规划、世界模型和动作模型串联会产生接口瓶颈与误差累积。",
        "VLM和视频生成模型负责理解、规划、进度和未来状态；Action Generation Model把子目标与共享上下文转换为动作chunk，四阶段逐步训练后联合微调。",
        ["理解多模态指令", "预测未来视觉状态", "分解长程子目标", "生成连续动作chunk"],
        ["LIBERO-Plus零样本平均成功率89.6%", "RoboTwin 2.0 Clean/Rand约93.68%/93.16%"],
        ["其脑-小脑分层可映射为Qwen规划+确定性车控执行器", "提示未来Action通道应共享感知上下文但不能绕过安全门"],
        ["机器人动作空间与车控工具不同", "模型规模、权重许可和车规安全仍需单独评估"],
        "partial", "https://github.com/iFLYTEK-Embodied-Robotics-Team/iFLYTEK-Embodied-Omni",
        note="项目仓库公开，需核验权重和完整训练代码。"),
    "c4b1e6b1f2": row(
        "ReflectWorld-MM把开放视频流组织成实体中心的情节、语义和程序记忆，而不是把所有帧塞进上下文。",
        "平坦向量库围绕帧检索，难以追踪同一乘员/物体跨时间重现和变化。",
        "有界短期感知先解析实体；长期层维护多尺度episodic、演化的entity semantic和procedural memory，并持久化到索引数据库供Agent查询。",
        ["接入RTSP/摄像头流", "解析事件和重复实体", "写入分层持久记忆", "Agent按证据查询变化"],
        ["论文报告六个长视频/终身记忆基准均取得最佳准确率"],
        ["适合长期记住乘员、物品位置和座舱事件，同时避免视觉KV无限增长", "可作为视觉侧外部记忆服务"],
        ["持续摄像带来隐私和存储边界", "身份合并错误会污染长期记忆"],
        "open", "https://github.com/addxai/ReflectWorld",
        note="Apache-2.0代码和可运行服务已公开。"),
    "357d87176e": row(
        "ARDena通过持久用户上下文与动态场景约束分层拼装prompt，在不微调模型时控制实时多模态Agent行为。",
        "实时Agent需求频繁变化，重新微调慢；单一超长prompt又难维护和审计。",
        "Prompt Construction Engine在事件循环中组合长期用户上下文、当前场景规则和交互状态，约束语音、视觉、工具和Avatar输出。",
        ["读取持久上下文", "注入场景规则", "构造本轮受限prompt", "执行工具并更新状态"],
        ["论文报告不同场景定义能稳定改变行为并维持实时运行；公开摘要未提供足够数值结果"],
        ["可把驾驶、驻车、儿童在车等模式做成独立场景策略层", "适合限制每个场景可见工具和口播风格"],
        ["prompt控制不是安全证明，车控仍需确定性Policy Gate", "Unity实现与当前Python栈需适配"],
        "unknown", note="论文与相关原型信息公开，官方实现对应关系需核验。"),
    "1181cb0b20": row(
        "OmniVideo-100K用实体锚定脚本和证据链生成10万音视频QA，强化跨片段、跨模态推理。",
        "独立给音频和视频做caption会切断声源与画面实体关系，分段还会导致实体指代漂移。",
        "先生成全局摘要、主实体和分段音视频脚本，再从跨段多模态线索生成QA与证据链；同时发布人工核验测试集。",
        ["分离并低采样音视频", "统一主实体与说话人", "生成结构化脚本", "挖掘证据链并生成QA"],
        ["含5214个视频、10万QA和505条人工测试", "Qwen3-Omni-30B微调后OmniVideo-Test提升约13.86%"],
        ["可用于构造座舱音视频联合测试，防止视觉和语音各自理解却不建立关系", "可作为未来Qwen3-Omni视觉流微调数据引擎模板"],
        ["主要是离线长视频QA，不直接评测实时打断和响应时机", "自动数据引擎需要多模型/API成本"],
        "open", "https://github.com/MiG-NJU/OmniVideo-100K",
        note="代码、数据、测试集和部分微调模型已公开。"),
}


def main():
    with open(PATH, encoding="utf-8") as stream:
        payload = json.load(stream)
    payload.update(UPDATES)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=1)
        stream.write("\n")
    os.replace(tmp, PATH)
    with open(ITEMS_PATH, encoding="utf-8") as stream:
        items_payload = json.load(stream)
    for item in items_payload["items"]:
        explanation = UPDATES.get(item["id"])
        if explanation:
            fit = explanation.get("project_fit") or []
            item["summary_zh"] = (explanation["tl_dr"]
                                  + ((" " + fit[0]) if fit else ""))[:400]
    tmp = ITEMS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as stream:
        json.dump(items_payload, stream, ensure_ascii=False, indent=1)
        stream.write("\n")
    os.replace(tmp, ITEMS_PATH)
    print(f"editorial updates={len(UPDATES)} total={len(payload)}")


if __name__ == "__main__":
    main()
