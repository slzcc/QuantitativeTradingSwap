#***********************************************
#
#      Filename: math_modules.py
#
#        Author: shilei@hotstone.com.cn
#   Description: 数学模块
#
#        Create: 2022-12-20 17:31:00
# Last Modified: 2022-12-20 17:31:00
#
#***********************************************
import numpy as np
import math
import statsmodels.api as sm

def ForwardPercentageCalculationMain(data, percentage=[]):
    """
    接收 list 并计算当前值对比前值
    :param data: list
    :return list

    ex: (33252817.1212 - 28779697.1913) / 33252817.1212 * 100 = 13.45185256
    [33252817.1212,
    28779697.1913,]
    """
    if len(data) < 2:
        pass
    elif len(data) == 2:
        calculation = (data[0] - data[1]) / data[0] * 100
        percentage.append(calculation)
    else:
        calculation = (data[0] - data[1]) / data[0] * 100
        percentage.append(calculation)
        ReversePercentageCalculationMain(data[1:], percentage)

def ReversePercentageCalculationMain(data, percentage=[]):
    """
    接收 list 并计算前值对比当前值
    :param data: list
    :return list

    ex: (28779697.1913 - 33252817.1212) / 28779697.1913 * 100 = -15.54262333
    [33252817.1212,
    28779697.1913,]
    """
    if len(data) < 2:
        pass
    elif len(data) == 2:
        calculation = (data[1] - data[0]) / data[1] * 100
        percentage.append(calculation)
    else:
        calculation = (data[1] - data[0]) / data[1] * 100
        percentage.append(calculation)
        ForwardPercentageCalculationMain(data[1:], percentage)

def DegreeOfAngleBetweenThreePointsMain(data, degree=[]):
    """
    三点之间的夹角
    :param data: list
    :return list
    """
    if len(data) < 3:
        return [0]
    elif len(data) == 3:
        calculation = CalAngle([(0, data[0]), (1, data[1]), (2, data[2])])
        degree.append(calculation)
        return degree
    else:
        calculation = CalAngle([(0, data[0]), (1, data[1]), (2, data[2])])
        degree.append(calculation)
        return DegreeOfAngleBetweenThreePointsMain(data[1:], degree)

def CalAngle(point):
    """
    Docs https://blog.csdn.net/shengyutou/article/details/119670615
    根据三点坐标计算夹角

                  点a
           点b ∠
                   点c

    :param point_a、point_b、point_c: 数据类型为 list, 二维坐标形式 [x、y] 或三维坐标形式 [x、y、z]
    :return: 返回角点b的夹角值

    数学原理：
    设 m,n 是两个不为 0 的向量，它们的夹角为 <m, n> (或用α ,β, θ ,..,字母表示)

    1、由向量公式：cos <m,n> = m.n / |m||n|

    2、若向量用坐标表示，m = (x1, y1, z1), n = (x2, y2, z2),

    则, m.n = (x1x2 + y1y2 + z1z2).

    |m| = √(x1^2 + y1^2 + z1^2), |n|= √(x2^2 + y2^2 + z2^2).

    将这些代入 ② 得到：

    cos <m,n> = (x1x2 + y1y2 + z1z2) / [√(x1^2 + y1^2 + z1^2) * √(x2^2 + y2^2 + z2^2)]

    上述公式是以空间三维坐标给出的, 令坐标中的z=0,则得平面向量的计算公式。

    两个向量夹角的取值范围是: [0,π].

    夹角为锐角时, cosθ > 0；夹角为钝角时, cosθ < 0.

    """
    point_a = point[0]
    point_b = point[1]
    point_c = point[2]

    a_x, b_x, c_x = point_a[0], point_b[0], point_c[0]  # 点a、b、c的x坐标
    a_y, b_y, c_y = point_a[1], point_b[1], point_c[1]  # 点a、b、c的y坐标

    if len(point_a) == len(point_b) == len(point_c) == 3:
        # print("坐标点为3维坐标形式")
        a_z, b_z, c_z = point_a[2], point_b[2], point_c[2]  # 点a、b、c的z坐标
    else:
        a_z, b_z, c_z = 0, 0, 0  # 坐标点为2维坐标形式，z 坐标默认值设为0
        # print("坐标点为2维坐标形式，z 坐标默认值设为0")

    # 向量 m=(x1,y1,z1), n=(x2,y2,z2)
    x1,y1,z1 = (a_x - b_x), (a_y - b_y), (a_z - b_z)
    x2,y2,z2 = (c_x - b_x), (c_y - b_y), (c_z - b_z)

    # 两个向量的夹角，即角点b的夹角余弦值
    cos_b = (x1 * x2 + y1 * y2 + z1 * z2) / (math.sqrt(x1 ** 2 + y1 ** 2 + z1 ** 2) * (math.sqrt(x2 ** 2 + y2 ** 2 + z2 ** 2))) # 角点b的夹角余弦值
    B = math.degrees(math.acos(cos_b)) # 角点b的夹角值
    return B

def angle_between(point):
    """
    与方法 CalAngle 方法相似，但结果不一致
    """
    x1, y1 = point[0]
    x2, y2 = point[1]
    x3, y3 = point[2]

    v21 = (x1 - x2, y1 - y2)
    v23 = (x3 - x2, y3 - y2)

    dot = v21[0] * v23[0] + v21[1] * v23[1]
    det = v21[0] * v23[1] - v21[1] * v23[0]

    theta = np.rad2deg(np.arctan2(det, dot))

    return theta

def azimuthangle(x1, y1, x2, y2):
    """ 已知两点坐标计算角度 -
    :param x1: 原点横坐标值
    :param y1: 原点纵坐标值
    :param x2: 目标点横坐标值
    :param y2: 目标纵坐标值
    """
    angle = 0.0
    dx = x2 - x1
    dy = y2 - y1
    if x2 == x1:
        angle = math.pi / 2.0
        if y2 == y1:
            angle = 0.0
        elif y2 < y1:
            angle = 3.0 * math.pi / 2.0
    elif x2 > x1 and y2 > y1:
        angle = math.atan(dx / dy)
    elif x2 > x1 and y2 < y1:
        angle = math.pi / 2 + math.atan(-dy / dx)
    elif x2 < x1 and y2 < y1:
        angle = math.pi + math.atan(dx / dy)
    elif x2 < x1 and y2 > y1:
        angle = 3.0 * math.pi / 2.0 + math.atan(dy / -dx)
    return angle * 180 / math.pi

def mk_test(x, alpha=0.05):
    """
    Docs https://dreamhomes.top/posts/202202161704/
    Github https://github.com/mmhs013/pyMannKendall

    This function is derived from code originally posted by Sat Kumar Tomer
    (satkumartomer@gmail.com)
    See also: http://vsp.pnnl.gov/help/Vsample/Design_Trend_Mann_Kendall.htm
    The purpose of the Mann-Kendall (MK) test (Mann 1945, Kendall 1975, Gilbert
    1987) is to statistically assess if there is a monotonic upward or downward
    trend of the variable of interest over time. A monotonic upward (downward)
    trend means that the variable consistently increases (decreases) through
    time, but the trend may or may not be linear. The MK test can be used in
    place of a parametric linear regression analysis, which can be used to test
    if the slope of the estimated linear regression line is different from
    zero. The regression analysis requires that the residuals from the fitted
    regression line be normally distributed; an assumption not required by the
    MK test, that is, the MK test is a non-parametric (distribution-free) test.
    Hirsch, Slack and Smith (1982, page 107) indicate that the MK test is best
    viewed as an exploratory analysis and is most appropriately used to
    identify stations where changes are significant or of large magnitude and
    to quantify these findings.
    Input:
        x:   a vector of data
        alpha: significance level (0.05 default)
    Output:
        trend: tells the trend (increasing, decreasing or no trend)
        h: True (if trend is present) or False (if trend is absence)
        p: p value of the significance test
        z: normalized test statistics
    Examples
    --------
      >>> x = np.random.rand(100)
      >>> trend,h,p,z = mk_test(x,0.05)
    """
    n = len(x)

    # calculate S
    s = 0
    for k in range(n - 1):
        for j in range(k + 1, n):
            s += np.sign(x[j] - x[k])

    # calculate the unique data
    unique_x, tp = np.unique(x, return_counts=True)
    g = len(unique_x)

    # calculate the var(s)
    if n == g:  # there is no tie
        var_s = (n * (n - 1) * (2 * n + 5)) / 18
    else:  # there are some ties in data
        var_s = (n * (n - 1) * (2 * n + 5) - np.sum(tp * (tp - 1) * (2 * tp + 5))) / 18

    if s > 0:
        z = (s - 1) / np.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / np.sqrt(var_s)
    else:  # s == 0:
        z = 0

    # calculate the p_value
    p = 2 * (1 - norm.cdf(abs(z)))  # two tail test
    h = abs(z) > norm.ppf(1 - alpha / 2)

    if (z < 0) and h:
        trend = 'decreasing'
    elif (z > 0) and h:
        trend = 'increasing'
    else:
        trend = 'no trend'
    return trend, h, p, z

def filter_extreme_percent(series, min=0.25, max=0.75):
    """
    中位数 因子取极值
    """
    series = series.sort_values()
    q = series.quantile([min, max])
    return np.clip(series, q.iloc[0], q.iloc[1])

def filter_extreme_mad(series, n):
    """
    MAD 因子取极值
    """
    median = series.quantile(0.5)
    mad = ((series - median).abs()).quantile(0.5)
    max_range = median + n * mad
    min_range = median - n * mad
    return np.clip(series, min_range, max_range)

def filter_extreme_3sigma(series, n=3):
    """
    3sigma 因子取极值
    """
    mean = series.mean()
    std = series.std()
    max_range = mean + n * std
    min_range = mean - n * std
    return np.clip(series, min_range, max_range)

def standard(series):
    """
    标准化操作
    """
    mean = series.mean()
    std = series.mean()
    return (series - mean) / std

def neutral(factor, market_cap):
    """
    中性操作
    """
    y = factor
    x = market_cap
    result = sm.OLS(y.astype(float), x.astype(float)).fit()
    return result.resid