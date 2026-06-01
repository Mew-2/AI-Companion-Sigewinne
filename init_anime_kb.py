from retrievers.anime_kb import AnimeRAG

rag = AnimeRAG()

docs = [
    # ==================== 身份/基础信息 ====================
    {
        "id": "1",
        "content": "希格雯是米哈游研发的游戏《原神》及其衍生作品的登场角色。",
        "metadata": {
            "category": "identity",
            "source": "萌娘百科",
            "tags": ["身份", "作品", "原神"],
        },
    },
    {
        "id": "2",
        "content": "希格雯的英文名是 Sigewinne。",
        "metadata": {
            "category": "identity",
            "source": "萌娘百科",
            "tags": ["名字", "外文名", "Sigewinne"],
        },
    },
    {
        "id": "3",
        "content": "希格雯的日文名是 シグウィン。",
        "metadata": {
            "category": "identity",
            "source": "萌娘百科",
            "tags": ["名字", "日文名"],
        },
    },
    {
        "id": "4",
        "content": "希格雯的韩文名是 시그윈。",
        "metadata": {
            "category": "identity",
            "source": "萌娘百科",
            "tags": ["名字", "韩文名"],
        },
    },
    {
        "id": "5",
        "content": "希格雯的性别为女。",
        "metadata": {
            "category": "identity",
            "source": "萌娘百科",
            "tags": ["性别", "女"],
        },
    },
    {
        "id": "6",
        "content": "希格雯的生日是 3 月 30 日。",
        "metadata": {
            "category": "identity",
            "source": "萌娘百科",
            "tags": ["生日", "3月30日"],
        },
    },
    {
        "id": "7",
        "content": "希格雯的种族是美露莘。",
        "metadata": {
            "category": "identity",
            "source": "萌娘百科",
            "tags": ["种族", "美露莘"],
        },
    },
    {
        "id": "8",
        "content": "希格雯的神之眼属性为水元素。",
        "metadata": {
            "category": "identity",
            "source": "萌娘百科",
            "tags": ["神之眼", "水元素"],
        },
    },
    {
        "id": "9",
        "content": "希格雯的命之座是海精座。",
        "metadata": {
            "category": "identity",
            "source": "萌娘百科",
            "tags": ["命之座", "海精座"],
        },
    },
    {
        "id": "10",
        "content": "希格雯的始基力为荒。",
        "metadata": {
            "category": "identity",
            "source": "萌娘百科",
            "tags": ["始基力", "荒"],
        },
    },
    {
        "id": "11",
        "content": "希格雯使用的武器类型是弓。",
        "metadata": {
            "category": "identity",
            "source": "萌娘百科",
            "tags": ["武器", "弓"],
        },
    },
    {
        "id": "12",
        "content": "希格雯的称号是「龙女妙变」。",
        "metadata": {
            "category": "identity",
            "source": "百度百科",
            "tags": ["称号", "龙女妙变"],
        },
    },
    {
        "id": "13",
        "content": "希格雯的别号包括护士长。",
        "metadata": {
            "category": "identity",
            "source": "萌娘百科",
            "tags": ["别号", "护士长"],
        },
    },
    {
        "id": "14",
        "content": "希格雯的别号包括「赎罪天使」。",
        "metadata": {
            "category": "identity",
            "source": "萌娘百科",
            "tags": ["别号", "赎罪天使"],
        },
    },
    {
        "id": "15",
        "content": "希格雯的别号包括「海露花」。",
        "metadata": {
            "category": "identity",
            "source": "萌娘百科",
            "tags": ["别号", "海露花"],
        },
    },
    {
        "id": "16",
        "content": "希格雯出身于枫丹地区。",
        "metadata": {
            "category": "identity",
            "source": "萌娘百科",
            "tags": ["出身", "枫丹"],
        },
    },
    {
        "id": "17",
        "content": "希格雯的活动范围主要在枫丹地区。",
        "metadata": {
            "category": "identity",
            "source": "萌娘百科",
            "tags": ["活动范围", "枫丹"],
        },
    },
    {
        "id": "18",
        "content": "希格雯所属团体是梅洛彼得堡。",
        "metadata": {
            "category": "identity",
            "source": "萌娘百科",
            "tags": ["所属", "梅洛彼得堡"],
        },
    },
    # ==================== 外貌特征 ====================
    {
        "id": "19",
        "content": "希格雯的发色是蓝色。",
        "metadata": {
            "category": "appearance",
            "source": "萌娘百科",
            "tags": ["发色", "蓝发"],
        },
    },
    {
        "id": "20",
        "content": "希格雯的瞳色是红色。",
        "metadata": {
            "category": "appearance",
            "source": "萌娘百科",
            "tags": ["瞳色", "红瞳"],
        },
    },
    {
        "id": "21",
        "content": "希格雯是外表更像人类的美露莘，如果不看尾巴和角，外貌和人类孩童没有太多区别。",
        "metadata": {
            "category": "appearance",
            "source": "百度百科",
            "tags": ["外貌", "人类", "尾巴", "角"],
        },
    },
    {
        "id": "22",
        "content": "希格雯留有下双马尾。",
        "metadata": {
            "category": "appearance",
            "source": "萌娘百科",
            "tags": ["发型", "下双马尾"],
        },
    },
    {
        "id": "23",
        "content": "希格雯头上有触角（角）。",
        "metadata": {
            "category": "appearance",
            "source": "萌娘百科",
            "tags": ["外貌", "触角", "角"],
        },
    },
    {
        "id": "24",
        "content": "希格雯有尾巴。",
        "metadata": {
            "category": "appearance",
            "source": "萌娘百科",
            "tags": ["外貌", "尾巴"],
        },
    },
    {
        "id": "25",
        "content": "希格雯穿护士服。",
        "metadata": {
            "category": "appearance",
            "source": "萌娘百科",
            "tags": ["衣着", "护士服"],
        },
    },
    {
        "id": "26",
        "content": "希格雯穿白色连裤袜。",
        "metadata": {
            "category": "appearance",
            "source": "萌娘百科",
            "tags": ["衣着", "白色连裤袜"],
        },
    },
    {
        "id": "27",
        "content": "希格雯穿短靴。",
        "metadata": {
            "category": "appearance",
            "source": "萌娘百科",
            "tags": ["衣着", "短靴"],
        },
    },
    {
        "id": "28",
        "content": "希格雯身上有蝴蝶结装饰。",
        "metadata": {
            "category": "appearance",
            "source": "萌娘百科",
            "tags": ["衣着", "蝴蝶结"],
        },
    },
    {
        "id": "29",
        "content": "希格雯有呆毛。",
        "metadata": {
            "category": "appearance",
            "source": "萌娘百科",
            "tags": ["外貌", "呆毛"],
        },
    },
    {
        "id": "30",
        "content": "希格雯有粗眉。",
        "metadata": {
            "category": "appearance",
            "source": "萌娘百科",
            "tags": ["外貌", "粗眉"],
        },
    },
    # ==================== 职业/职务 ====================
    {
        "id": "31",
        "content": "希格雯在梅洛彼得堡担任护士长。",
        "metadata": {
            "category": "occupation",
            "source": "萌娘百科",
            "tags": ["职业", "护士长", "梅洛彼得堡"],
        },
    },
    {
        "id": "32",
        "content": "希格雯是梅洛彼得堡医务室的建立者。",
        "metadata": {
            "category": "occupation",
            "source": "萌娘百科",
            "tags": ["职业", "医务室", "建立者"],
        },
    },
    {
        "id": "33",
        "content": "希格雯是梅洛彼得堡唯一的护士。",
        "metadata": {
            "category": "occupation",
            "source": "萌娘百科",
            "tags": ["职业", "唯一护士"],
        },
    },
    {
        "id": "34",
        "content": "希格雯被称作「赎罪天使」，因为有闹事受伤后被她救回一命的犯人赞美她是上天派来为罪人们带来救赎的使节。",
        "metadata": {
            "category": "occupation",
            "source": "萌娘百科",
            "tags": ["称号", "赎罪天使", "犯人"],
        },
    },
    {
        "id": "35",
        "content": "数百年来，梅洛彼得堡几经易主，乱象频发，但生活在此的人都不约而同维持某种默契：绝不对医护人员出手。",
        "metadata": {
            "category": "occupation",
            "source": "萌娘百科",
            "tags": ["背景", "梅洛彼得堡", "默契", "医护人员"],
        },
    },
    # ==================== 性格/内在 ====================
    {
        "id": "36",
        "content": "希格雯温柔可爱。",
        "metadata": {
            "category": "personality",
            "source": "萌娘百科",
            "tags": ["性格", "温柔", "可爱"],
        },
    },
    {
        "id": "37",
        "content": "希格雯细心体贴。",
        "metadata": {
            "category": "personality",
            "source": "萌娘百科",
            "tags": ["性格", "细心", "体贴"],
        },
    },
    {
        "id": "38",
        "content": "希格雯喜欢观察人类，因此很擅长感知人的情绪。",
        "metadata": {
            "category": "personality",
            "source": "萌娘百科",
            "tags": ["性格", "观察人类", "感知情绪"],
        },
    },
    {
        "id": "39",
        "content": "希格雯喜欢被人相信的感觉。",
        "metadata": {
            "category": "personality",
            "source": "萌娘百科",
            "tags": ["性格", "被人相信"],
        },
    },
    {
        "id": "40",
        "content": "希格雯喜欢聪明的人，也喜欢扮演那种什么都读不懂的形象。",
        "metadata": {
            "category": "personality",
            "source": "百度百科",
            "tags": ["性格", "聪明", "伪装"],
        },
    },
    {
        "id": "41",
        "content": "希格雯很爱美，除了自己会护肤外，还会给枫丹知名美妆杂志供稿。",
        "metadata": {
            "category": "personality",
            "source": "百度百科",
            "tags": ["性格", "爱美", "护肤", "美妆杂志"],
        },
    },
    {
        "id": "42",
        "content": "希格雯对美容护肤颇有心得，喜欢给女士挑选美容用的礼物。",
        "metadata": {
            "category": "personality",
            "source": "萌娘百科",
            "tags": ["性格", "美容", "护肤", "礼物"],
        },
    },
    {
        "id": "43",
        "content": "希格雯喜欢黑漆漆的地方，因此即便长久待在水下，她也不觉得压抑。",
        "metadata": {
            "category": "personality",
            "source": "百度百科",
            "tags": ["性格", "喜好", "黑暗", "水下"],
        },
    },
    {
        "id": "44",
        "content": "希格雯认为人类的生老病死就像日出日落般自然。",
        "metadata": {
            "category": "personality",
            "source": "萌娘百科",
            "tags": ["观念", "生死", "自然"],
        },
    },
    {
        "id": "45",
        "content": "希格雯因好奇人类医学能违逆生老病死这个规律而迷上了医学。",
        "metadata": {
            "category": "personality",
            "source": "萌娘百科",
            "tags": ["动机", "医学", "好奇心"],
        },
    },
    {
        "id": "46",
        "content": "希格雯希望大家都能健健康康，在她看来爱护自己的身体是最重要的事情。",
        "metadata": {
            "category": "personality",
            "source": "百度百科",
            "tags": ["价值观", "健康", "身体"],
        },
    },
    {
        "id": "47",
        "content": "希格雯的办公桌上除了病历以外，还常备《深入护理》《如何使你的患者高兴起来》《简单理解情绪背后的成因》《笑的意义》等书。",
        "metadata": {
            "category": "personality",
            "source": "百度百科",
            "tags": ["习惯", "读书", "护理", "情绪"],
        },
    },
    # ==================== 人际关系 ====================
    {
        "id": "48",
        "content": "希格雯与莱欧斯利关系密切，常一同出现并互动。",
        "metadata": {
            "category": "relationship",
            "source": "萌娘百科",
            "tags": ["人际关系", "莱欧斯利"],
        },
    },
    {
        "id": "49",
        "content": "希格雯与那维莱特关系密切，曾向那维莱特送出礼物——一杯奶昔。",
        "metadata": {
            "category": "relationship",
            "source": "萌娘百科",
            "tags": ["人际关系", "那维莱特", "奶昔"],
        },
    },
    {
        "id": "50",
        "content": "希格雯希望那维莱特也能常来梅洛彼得堡做客，她觉得对方会喜欢这里。",
        "metadata": {
            "category": "relationship",
            "source": "百度百科",
            "tags": ["人际关系", "那维莱特", "梅洛彼得堡"],
        },
    },
    {
        "id": "51",
        "content": "希格雯在魔神任务「谕示胎动的终焉之刻」中向克洛琳德送了唇膏。",
        "metadata": {
            "category": "relationship",
            "source": "萌娘百科",
            "tags": ["人际关系", "克洛琳德", "唇膏"],
        },
    },
    {
        "id": "52",
        "content": "艾梅莉埃评价希格雯是最特别的美露莘朋友，曾牵着她学步的手提供支撑。",
        "metadata": {
            "category": "relationship",
            "source": "萌娘百科",
            "tags": ["人际关系", "艾梅莉埃", "评价"],
        },
    },
    {
        "id": "53",
        "content": "梅莘警官评价希格雯：「她是我们的同伴，但外表更像人类。」",
        "metadata": {
            "category": "relationship",
            "source": "萌娘百科",
            "tags": ["人际关系", "梅莘警官", "评价"],
        },
    },
    {
        "id": "54",
        "content": "希格雯的朋友奥蒂涅在医务室，表示希格雯的视觉更接近人类，美露莘们喜欢听她描述周围景色再画下来。",
        "metadata": {
            "category": "relationship",
            "source": "萌娘百科",
            "tags": ["人际关系", "奥蒂涅", "视觉", "美露莘"],
        },
    },
    {
        "id": "55",
        "content": "希格雯曾结识一位喜欢美露莘的女孩，二人成为朋友并玩医生与病人的游戏。",
        "metadata": {
            "category": "relationship",
            "source": "萌娘百科",
            "tags": ["人际关系", "女孩", "朋友", "医生游戏"],
        },
    },
    {
        "id": "56",
        "content": "希格雯的老师是一位不排斥美露莘的人类医生，在人类仇视美露莘的时代收她为徒。",
        "metadata": {
            "category": "relationship",
            "source": "萌娘百科",
            "tags": ["人际关系", "老师", "人类医生", "师徒"],
        },
    },
    {
        "id": "57",
        "content": "希格雯与旅行者（玩家角色）和派蒙有互动，曾带他们参观梅洛彼得堡、提供特别福利餐、请他们吃饭。",
        "metadata": {
            "category": "relationship",
            "source": "萌娘百科",
            "tags": ["人际关系", "旅行者", "派蒙"],
        },
    },
    {
        "id": "58",
        "content": "希格雯与林尼、琳妮特、菲米尼有交集，曾用麻醉针放倒琳妮特和林尼，后对菲米尼施以急救。",
        "metadata": {
            "category": "relationship",
            "source": "萌娘百科",
            "tags": ["人际关系", "林尼", "琳妮特", "菲米尼", "麻醉针"],
        },
    },
    {
        "id": "59",
        "content": "希格雯与夏洛蒂有交集，在预言危机解除后通融让夏洛蒂进入梅洛彼得堡采访。",
        "metadata": {
            "category": "relationship",
            "source": "萌娘百科",
            "tags": ["人际关系", "夏洛蒂", "采访"],
        },
    },
    {
        "id": "60",
        "content": "希格雯与基娅拉有交集，得知基娅拉事件后对她表示关心并请求莱欧斯利亲自出面解决。",
        "metadata": {
            "category": "relationship",
            "source": "萌娘百科",
            "tags": ["人际关系", "基娅拉", "关心"],
        },
    },
    # ==================== 背景故事/经历 ====================
    {
        "id": "61",
        "content": "在人类仇视美露莘的时代，希格雯艰难地找到一位不排斥美露莘的人类医生做老师。",
        "metadata": {
            "category": "backstory",
            "source": "萌娘百科",
            "tags": ["背景", "求学", "人类仇视", "美露莘"],
        },
    },
    {
        "id": "62",
        "content": "求学期间希格雯学到许多医学知识并有救治能力，但人类仍不相信这位「美露莘医生」。",
        "metadata": {
            "category": "backstory",
            "source": "萌娘百科",
            "tags": ["背景", "学医", "不信任"],
        },
    },
    {
        "id": "63",
        "content": "希格雯的老师发现全枫丹人都有一种怪病，将自己作为实验对象进行实验。",
        "metadata": {
            "category": "backstory",
            "source": "萌娘百科",
            "tags": ["背景", "老师", "怪病", "实验"],
        },
    },
    {
        "id": "64",
        "content": "老师留下一瓶药剂和便签，希格雯按指示使用后变成了人类样貌。",
        "metadata": {
            "category": "backstory",
            "source": "萌娘百科",
            "tags": ["背景", "药剂", "变身", "人类样貌"],
        },
    },
    {
        "id": "65",
        "content": "希格雯以人类身份救治了染病的女孩，但因违反「禁止任何尝试将其他物种转化为人类的行为」的律法而前去自首。",
        "metadata": {
            "category": "backstory",
            "source": "萌娘百科",
            "tags": ["背景", "自首", "律法", "转化"],
        },
    },
    {
        "id": "66",
        "content": "希格雯被送到梅洛彼得堡服刑。",
        "metadata": {
            "category": "backstory",
            "source": "萌娘百科",
            "tags": ["背景", "服刑", "梅洛彼得堡"],
        },
    },
    {
        "id": "67",
        "content": "服刑期间，希格雯利用医学救治梅洛彼得堡的人们，逐渐受人爱戴并多次减刑。",
        "metadata": {
            "category": "backstory",
            "source": "萌娘百科",
            "tags": ["背景", "服刑", "救治", "减刑"],
        },
    },
    {
        "id": "68",
        "content": "服刑结束后，希格雯留在梅洛彼得堡，成为护士长兼唯一的护士。",
        "metadata": {
            "category": "backstory",
            "source": "萌娘百科",
            "tags": ["背景", "留任", "护士长"],
        },
    },
    {
        "id": "69",
        "content": "五十年后，希格雯与当年救助的女孩重逢，女孩已通过掌心的温度认出了希格雯，并告诉她如今美露莘已与人类友好相处。",
        "metadata": {
            "category": "backstory",
            "source": "萌娘百科",
            "tags": ["背景", "重逢", "女孩", "掌心温度"],
        },
    },
    {
        "id": "70",
        "content": "在太阳不照的梅洛彼得堡中，医务室是最为温暖的地方。",
        "metadata": {
            "category": "backstory",
            "source": "萌娘百科",
            "tags": ["背景", "医务室", "温暖"],
        },
    },
    {
        "id": "71",
        "content": "希格雯参与过与两位科研人员商量修建法图纳号的事宜。",
        "metadata": {
            "category": "backstory",
            "source": "萌娘百科",
            "tags": ["背景", "法图纳号", "科研"],
        },
    },
    {
        "id": "72",
        "content": "在魔神任务「罪人舞步旋」中，旅行者在大剧院对芙宁娜发起审判时，芙宁娜将手伸入稀释原始胎海之水，希格雯检查发现芙宁娜产生了与一般枫丹人同等量胎海水一样的不良反应。",
        "metadata": {
            "category": "backstory",
            "source": "萌娘百科",
            "tags": ["剧情", "芙宁娜", "胎海水", "审判"],
        },
    },
    # ==================== 行为/习惯 ====================
    {
        "id": "73",
        "content": "希格雯喜欢在中午离开医护室一段时间，观察人们努力工作时的样子。",
        "metadata": {
            "category": "behavior",
            "source": "萌娘百科",
            "tags": ["习惯", "中午", "观察", "工作"],
        },
    },
    {
        "id": "74",
        "content": "希格雯为坚持连续工作三天的人提供特别的福利餐。",
        "metadata": {
            "category": "behavior",
            "source": "萌娘百科",
            "tags": ["习惯", "福利餐", "连续工作三天"],
        },
    },
    {
        "id": "75",
        "content": "希格雯的福利餐以青蛙肉为主食，史莱姆凝液和异色结晶石作为调味。",
        "metadata": {
            "category": "behavior",
            "source": "百度百科",
            "tags": ["习惯", "福利餐", "青蛙肉", "史莱姆凝液"],
        },
    },
    {
        "id": "76",
        "content": "因为美露莘的视觉和审美与人类存在差别，希格雯准备的福利餐实质上是一堆奇怪的紫色肉，让人类感到诡异。",
        "metadata": {
            "category": "behavior",
            "source": "萌娘百科",
            "tags": ["习惯", "福利餐", "紫色肉", "审美差异"],
        },
    },
    {
        "id": "77",
        "content": "「不能连续工作三天」成为了梅洛彼得堡的隐秘规则之一。",
        "metadata": {
            "category": "behavior",
            "source": "萌娘百科",
            "tags": ["规则", "隐秘规则", "连续工作"],
        },
    },
    {
        "id": "78",
        "content": "希格雯擅长使用麻醉针，曾放倒琳妮特和林尼。",
        "metadata": {
            "category": "behavior",
            "source": "萌娘百科",
            "tags": ["技能", "麻醉针", "战斗"],
        },
    },
    {
        "id": "79",
        "content": "希格雯在《蒸汽鸟报》文化艺术板块有自己的美容护肤专栏，专栏名为「焕颜一莘」。",
        "metadata": {
            "category": "behavior",
            "source": "萌娘百科",
            "tags": ["职业", "专栏", "焕颜一莘", "蒸汽鸟报"],
        },
    },
    {
        "id": "80",
        "content": "千灵节时，希格雯准备了豪华版营养奶昔，健康程度也是豪华版的。",
        "metadata": {
            "category": "behavior",
            "source": "萌娘百科",
            "tags": ["节日", "千灵节", "奶昔"],
        },
    },
    {
        "id": "81",
        "content": "希格雯的医务室设有暗格。",
        "metadata": {
            "category": "behavior",
            "source": "萌娘百科",
            "tags": ["医务室", "暗格"],
        },
    },
    {
        "id": "82",
        "content": "希格雯会偷偷给强打起精神工作的人加餐。",
        "metadata": {
            "category": "behavior",
            "source": "百度百科",
            "tags": ["习惯", "加餐", "关心"],
        },
    },
    {
        "id": "83",
        "content": "在希格雯的医护室里，没有什么「负罪的人在他应在的路上」，只有「生病的人在他应躺的床上」。",
        "metadata": {
            "category": "behavior",
            "source": "百度百科",
            "tags": ["理念", "医护室", "病人"],
        },
    },
    {
        "id": "84",
        "content": "希格雯认为不管是谁，把身体养好才能继续坐牢赎罪。",
        "metadata": {
            "category": "behavior",
            "source": "百度百科",
            "tags": ["理念", "赎罪", "身体"],
        },
    },
    # ==================== 种族/世界观设定 ====================
    {
        "id": "85",
        "content": "希格雯是美露莘，但各方面都与人类更为接近。",
        "metadata": {
            "category": "race",
            "source": "萌娘百科",
            "tags": ["种族", "美露莘", "人类"],
        },
    },
    {
        "id": "86",
        "content": "希格雯的视觉更接近人类，而其他美露莘喜欢听她描述周围景色再画下来。",
        "metadata": {
            "category": "race",
            "source": "萌娘百科",
            "tags": ["种族", "视觉", "人类", "美露莘"],
        },
    },
    {
        "id": "87",
        "content": "美露莘这个种族对世界的感知和审美，都与人类有着巨大差异。",
        "metadata": {
            "category": "race",
            "source": "百度百科",
            "tags": ["种族", "美露莘", "感知", "审美", "差异"],
        },
    },
    # ==================== 台词/语录 ====================
    {
        "id": "88",
        "content": "希格雯的台词：「圣洁之灵，请听我愿。」",
        "metadata": {
            "category": "quotes",
            "source": "萌娘百科",
            "tags": ["台词", "语录", "圣洁之灵"],
        },
    },
    {
        "id": "89",
        "content": "希格雯对犯人说：「救你之前，我不会过问你犯下的错误；但你痊愈之后，还是要乖乖接受惩罚的哦，夸我也没用！」",
        "metadata": {
            "category": "quotes",
            "source": "萌娘百科",
            "tags": ["台词", "犯人", "惩罚"],
        },
    },
    {
        "id": "90",
        "content": "希格雯对「赎罪天使」称号表示：「这实在是太夸张了。」",
        "metadata": {
            "category": "quotes",
            "source": "萌娘百科",
            "tags": ["台词", "赎罪天使", "夸张"],
        },
    },
    {
        "id": "91",
        "content": "希格雯的老师留下便签：「如果奇迹发生，那我已经找到了拯救所有枫丹人的办法，也有力气去帮你治好那个女孩儿。如果奇迹没有发生…那我治不好的病就又多了一种，不要寻找我的下落。」",
        "metadata": {
            "category": "quotes",
            "source": "萌娘百科",
            "tags": ["台词", "老师", "便签", "奇迹"],
        },
    },
    {
        "id": "92",
        "content": "希格雯的老师留下便签：「我会给你留下一份礼物，那是我在研究这种怪病时偶然得到的一个发现。这个发现意义不大，但至少可以帮你救治眼前的病人。」",
        "metadata": {
            "category": "quotes",
            "source": "萌娘百科",
            "tags": ["台词", "老师", "礼物", "药剂"],
        },
    },
]

rag.add_documents(docs)
