"""Stopword lists for English and Bangla (small, hand-curated)."""

from __future__ import annotations

ENGLISH = frozenset(
    """
a about above after again against all also am an and any are aren't as at be because been
before being below between both but by can can't cannot could couldn't did didn't do does
doesn't doing don't down during each few for from further get gets got had hadn't has hasn't
have haven't having he her here hers herself him himself his how i if in into is isn't it
it's its itself just let's like make may me more most much must my myself no nor not of off
on once one only or other ought our ours ourselves out over own same say says shan't she
should shouldn't so some such than that the their theirs them themselves then there these
they this those through to too under until up us use used using very was wasn't we were
weren't what when where which while who whom why will with won't would wouldn't yes yet you
your yours yourself yourselves via per etc ie eg new way ways need needs want even many
every well still back first last also may might will shall however therefore thus
""".split()
)

BANGLA = frozenset(
    """
অথবা অনেক অনেকে অনেকেই অন্য অবশ্য অবধি আগে আছে আজ আবার আমরা আমাদের আমার আমি আর আরও ইত্যাদি
ইহা উচিত উত্তর উনি উপর উপরে এ এঁদের এঁরা এই এক একটি একটা একবার এখন এখনও এখানে এখানেই এছাড়া
এটা এটি এত এতটাই এতে এদের এবং এবার এমন এমনকি এর এরা এস ও ওই ওকে ওখানে ওদের ওর ওরা কখনও
কত কবে কম করা করে করেছে করেছিল করেন করবে করলে করি করিয়া কয়েক কাছে কাজ কারণ কি কিংবা কিছু কিছুই
কিন্তু কী কে কেউ কেউই কেন কোন কোনও কোনো ক্ষেত্রে খুব গিয়ে গিয়েছে গেছে গেল গেলে গোটা চলে চান চায়
ছাড়া ছাড়াও ছিল ছিলেন জন জানা জানিয়ে জানিয়েছে জন্য জন্যওজে তখন তবে তবু তরুণ তা তাঁকে তাঁদের তাঁর
তাঁরা তাই তাও তাকে তাতে তাদের তার তারপর তারা তারই তাহলে তিনি তুমি তো তোমার থাকবে থাকা থাকে থেকে
থেকেই দিকে দিতে দিয়ে দিয়েছে দিয়েছেন দিলেন দু দুই দুটি দুটো দেওয়া দেওয়ার দেখা দেখে দেন দ্বারা ধরা
ধরে ধামার নতুন নয় না নাই নাকি নাগাদ নানা নিজে নিজেই নিজেদের নিতে নিয়ে নিয়েছে নেই নেওয়া নেওয়ার
পক্ষে পর পরে পারি পারে পারেন পেয়ে পেয়েছে পর্যন্ত পাওয়া পি প্রতি প্রথম প্রভৃতি প্রযন্ত ফলে ফের বক্তব্য
বদলে বন বরং বলতে বলল বললেন বলা বলে বলেছেন বলেন বসে বহু বা বাদে বার বি বিনা বিভিন্ন বিশেষ বিষয়টি
বেশ বেশি ব্যবহার ব্যাপারে ভাবে ভাবেই মতো মতোই মধ্যভাগে মধ্যে মধ্যেই মধ্যেও মনে মাত্র মাধ্যমে মোট মোটেই
যখন যত যতটা যথেষ্ট যদি যদিও যা যাঁর যাঁরা যাওয়া যাওয়ার যাকে যাচ্ছে যাতে যাদের যান যাবে যায় যার যারা
যিনি যে যেখানে যেতে যেন যেমন রকম রয়েছে রাখা রেখে লক্ষ শুধু শুরু সঙ্গে সঙ্গেও সব সবার সমস্ত সম্প্রতি
সহ সহিত সাধারণ সামনে সি সুতরাং সে সেই সেখান সেখানে সেটা সেটাই সেটাও সেটি স্পষ্ট স্বয়ং হইতে হইবে
হইয়া হওয়া হওয়ায় হওয়ার হচ্ছে হত হতে হতেই হন হবে হবেন হয় হয়তো হয়নি হয়ে হয়েই হয়েছিল হয়েছে হাজার
হয়েছেন হল হলে হলেই হলেও হলো হিসাব হিসেবে হৈলে হোক হয়
""".split()
)

ALL = ENGLISH | BANGLA


def is_stopword(token: str) -> bool:
    return token in ALL
