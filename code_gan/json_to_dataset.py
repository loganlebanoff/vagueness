#!/usr/bin/env python
# -*- coding: utf-8 -*-

import matplotlib.pyplot as plt
import math
import yaml
import numpy
import numpy as np
import codecs
import operator
import h5py
import gensim
from gensim.models.word2vec import Word2Vec
from numpy import nan_to_num
import argparse

numpy.random.seed(123)
from keras.preprocessing.text import Tokenizer
from keras.preprocessing.sequence import pad_sequences

#if using theano, then comment the next line and uncomment the following 2 lines
float_type = numpy.float32        
# import theano
# float_type = theano.config.floatX

parser = argparse.ArgumentParser()
parser.add_argument('--VOCAB_SIZE', default=5000, type=int,
                            help='Number of words in the vocabulary.')
args = parser.parse_args()
 
vocab_size = args.VOCAB_SIZE
embedding_dim = 300
maxlen = 50
batch_size = 128
val_samples = batch_size * 10
num_folds = 5
train_ratio = 0.8
validation_ratio = 0.1
vague_phrase_threshold = 2
min_vague_score = 1
max_vague_score = 5

train_file = '../data/Privacy_Sentences.txt'
word_id_file = '../data/train.h5'
dict_file = '../data/words.dict'
embedding_file = '../data/GoogleNews-vectors-negative300.bin'
vague_file = '../data/vague_terms'
dataset_file = '../data/annotated_dataset_' + str(vocab_size) + '.h5'
# embedding_weights_file = '../data/annotated_embedding_weights_' + str(vocab_size) + '.h5'
clean_data_json = '../data/clean_data.json'
vague_phrases_file = '../data/vague_phrases.txt'
sentence_level_figure_file = '../data/sentence_level_distribution.png'


'''
Parameters
----------------
sentence: string
vague_phrases: dict, representing the counts of each vague phrase in the sentence

Output
----------------
labels: list of integers (0 or 1), one element for each word in the sentence
    0 = not a vague word
    1 = vague word
count: number of vague terms in sentence
'''

def addLists(list1, list2):
    if len(list1) != len(list2):
        raise Exception('Lists are not equal length')
    return [sum(x) for x in zip(list1, list2)]

def markOccurencesOfPhrase(sentence, phrase, count):
    phrase_counts = [0] * len(sentence)
    for i in range(len(sentence)):
        if i + len(phrase) >= len(sentence): break
        if sentence[i:i+len(phrase)] ==  phrase:
            for j in range(i, i+len(phrase)):
                phrase_counts[j] += count
    return phrase_counts

def didFindPhrase(phrase_counts):
    return sum(phrase_counts) > 0

def markOccurencesForEachWord(sentence, phrase, count):
    phrase_counts = [0] * len(sentence)
    for word in phrase:
        word_counts = markOccurencesOfPhrase(sentence, [word], count)
        phrase_counts = addLists(phrase_counts, word_counts)
    return phrase_counts
        
def labelVagueWords(sentence, vague_phrases):
    selected = [0] * len(sentence)
    for phrase, count in vague_phrases.iteritems():
        phrase = phrase.lower().strip().split()
        phrase_counts = markOccurencesOfPhrase(sentence, phrase, count)
        if not didFindPhrase(phrase_counts):
            phrase_counts = markOccurencesForEachWord(sentence, phrase, count)
        selected = addLists(selected, phrase_counts)
    labels = [1 if sel >= vague_phrase_threshold else 0 for sel in selected]
    if len(labels) != len(sentence):
        raise ValueError('len labels does not equal len sentence')
    return labels

# read in existing dictionary created by preprocess_unannotated.py
print('loading dictionary')
d = {}
with open(dict_file) as f:
    for line in f:
       (val, key) = line.split()
       d[val] = int(key)

# Reads in the JSON data
with open(clean_data_json) as f:
    json_str = f.read()
data = yaml.safe_load(json_str)

# calculate statistics
total_vague_terms = 0
total_terms = 0
total_vague_sents = 0
stds = []
num_vague_terms_list = []

# load file, one sentence per line
sentences = []
Y_sentence = []
Y_word = []
sentence_doc_ids = []
vague_phrases = {}
start_tag = ['<s>']
end_tag = ['</s>']
for doc in data['docs']:
    for sent in doc['vague_sentences']:
        words = sent['sentence_str'].lower().strip().split()
        if len(words) == 0:
            continue
        words = start_tag + words + end_tag
        sentences.append(' '.join(words))
        
        # Get the sentence-level scores
        scores = map(int, sent['scores'])
        Y_sentence.append(numpy.nan_to_num(numpy.average(scores)))
        
        # Get word-level vagueness
        word_labels = labelVagueWords(words, sent['vague_phrases'])
        Y_word.append(word_labels)
        
        # Store the document ID
        sentence_doc_ids.append(int(doc['id']))
        
        # Calculate statistics
        total_terms += len(word_labels)
        num_vague_words = sum(word_labels)
        total_vague_terms += num_vague_words
        num_vague_terms_list.append(num_vague_words)
        if num_vague_words > 0: 
            total_vague_sents += 1
        std = numpy.std(scores)
        stds.append(std)
        for phrase, count in sent['vague_phrases'].iteritems():
            if count >= vague_phrase_threshold:
                vague_phrases[phrase] = vague_phrases.get(phrase, 0) + 1
                
# Print statistics
print('total vague sentences: %d' % (total_vague_sents))
print('total number of sentences in train file: %d' % len(sentences))
print('total vague terms: %d' % (total_vague_terms))
print('total terms: %d' % (total_terms))
print('average standard deviation of scores for each sentence: %f' % (numpy.average(stds)))


# plt.hist(Y_sentence)
# plt.title("Sentence-Level Vagueness Score Distribution")
# plt.xlabel("Score")
# plt.ylabel("Number of Sentences")
# plt.show()

hist1, bins1 = np.histogram(Y_sentence, 8, (1,5))
hist2, bins2 = np.histogram(Y_sentence, 4, (1,5))
print('Histogram', [round(x, 3) for x in hist1/sum(hist1.astype(float))], bins1)
print('Histogram2', [round(x, 3) for x in hist2/sum(hist2.astype(float))], bins2)

bins = [0,1,2,3,4,5,6,100000]
num_vague_terms_histogram, _ = np.histogram(num_vague_terms_list, bins=bins)
num_vague_terms_probs = [1.*val/sum(num_vague_terms_histogram) for val in num_vague_terms_histogram]
print('Number of sentences with numbers of vague terms. ' + 
      'Last bin is all sentences with greater than 5 vague terms.', [round(x, 3) for x in num_vague_terms_probs], bins)
# convert from float to category (possible categories: {0,1,2,3})
for idx, item in enumerate(Y_sentence):
    res = math.floor(item)
    if res == max_vague_score:
        res = max_vague_score-1
    res -= 1
    Y_sentence[idx] = res
plt.hist(Y_sentence, bins=max_vague_score-min_vague_score, range=(min_vague_score-1, max_vague_score-1))
plt.title("Sentence-Level Vagueness Score Distribution")
plt.xlabel("Score")
plt.ylabel("Number of Sentences")
plt.show(block=False)
plt.savefig(sentence_level_figure_file)

sorted_vague_phrases = sorted(vague_phrases.items(), key=operator.itemgetter(1), reverse=True)
with open(vague_phrases_file, 'w') as f:
    for phrase, count in sorted_vague_phrases:
        if phrase != '':
            f.write(phrase + ': ' + str(count) + '\n')
            
word_id_seqs = []
for sent in sentences:
    words = sent.lower().split()
    word_id_seq = []
    for word in words:
        if (not d.has_key(word)) or (d[word] >= vocab_size):
            word_id_seq.append(0)
        else:
            word_id_seq.append(d[word])
    word_id_seqs.append(word_id_seq)
        
        
    
# # tokenize, create vocabulary
# tokenizer = Tokenizer(nb_words=vocab_size, filters=' ')
# tokenizer.fit_on_texts(sentences)
# word_id_seqs = tokenizer.texts_to_sequences(sentences)
# print('finished creating the dictionary')
    
# # output dictionary
# with codecs.open(dict_file, 'w') as outfile:
#     for word, idx in sorted(tokenizer.word_index.items(), key=operator.itemgetter(1)):
#         outfile.write('%s %d\n' % (word, idx))
#     
# # output list of word ids
# total_word_ids = 0
# my_word_ids = []
# for word_id_seq in word_id_seqs:
#     for word_id in word_id_seq[-maxlen-1:]: #TODO
#         total_word_ids += 1
#         my_word_ids.append(word_id)
#     
# outfile = h5py.File(word_id_file, 'w')
# states = outfile.create_dataset('words', data=numpy.array(my_word_ids))
# outfile.flush()
# outfile.close()

# # prepare embedding weights
# word2vec_model = Word2Vec.load_word2vec_format(embedding_file, binary=True)
# embedding_weights = numpy.zeros((vocab_size, embedding_dim), dtype=float_type)
#    
# n_words_in_word2vec = 0
# n_words_not_in_word2vec = 0
#    
# for word, idx in tokenizer.word_index.items():
#     if idx < vocab_size:
#         try: 
#             embedding_weights[idx,:] = word2vec_model[word]
#             n_words_in_word2vec += 1
#         except:
#             embedding_weights[idx,:] = 0.01 * numpy.random.randn(1, embedding_dim).astype(float_type)
#             n_words_not_in_word2vec += 1
# print('%d words found in word2vec, %d are not' % (n_words_in_word2vec, n_words_not_in_word2vec))
# outfile = h5py.File(embedding_weights_file, 'w')
# outfile.create_dataset('embedding_weights', data=embedding_weights)
# outfile.flush()
# outfile.close()

# weights used later for calculating the loss, so that it doesn't include padding
lengths = [len(seq) for seq in word_id_seqs]
weights = [[1]*length for length in lengths] 

# Pad X and Y
X = word_id_seqs
X_padded = pad_sequences(X, maxlen=maxlen, padding='post')
Y_padded_word = pad_sequences(Y_word, maxlen=maxlen, padding='post')
weights_padded = pad_sequences(weights, maxlen=maxlen, padding='post')
Y_sentence = numpy.asarray(Y_sentence, dtype=numpy.int32)
# Y_padded_word = Y_padded_word.reshape(Y_padded_word.shape[0], Y_padded_word.shape[1], 1)

# shuffle Documents
doc_ids = set()
for doc in data['docs']:
    doc_ids.add(int(doc['id']))
doc_ids = list(doc_ids)
numpy.random.shuffle(doc_ids)
train_len = int(train_ratio*len(doc_ids))
val_len = int(validation_ratio*len(doc_ids))

outfile = h5py.File(dataset_file, 'w')
outfile.create_dataset('X', data=X_padded)
outfile.create_dataset('Y', data=Y_sentence)
 
def get_all_except_one(my_list, exclude_idx):
    return [x for i,x in enumerate(my_list) if i!=exclude_idx]
 
folds = np.array_split(doc_ids,num_folds)
for fold_idx, fold in enumerate(folds):
    train_folds = get_all_except_one(folds, fold_idx)
    test_fold = fold
 
    def flatten_list_of_lists(list_of_lists):
        flatten = lambda l: [item for sublist in l for item in sublist]
        return flatten(list_of_lists)
    train_val_doc_ids = flatten_list_of_lists(train_folds)
    np.random.shuffle(train_val_doc_ids)
    val_doc_ids = train_val_doc_ids[:val_len]
    train_doc_ids = train_val_doc_ids[val_len:]
    test_doc_ids = test_fold
     
    # Split into train and test, keeping documents together
    train_indices = []
    val_indices = []
    test_indices = []
    for i in range(len(sentence_doc_ids)):
        doc = sentence_doc_ids[i]
        if doc in train_doc_ids:
            train_indices.append(i)
        elif doc in val_doc_ids:
            val_indices.append(i)
        elif doc in test_doc_ids:
            test_indices.append(i)
        else:
            raise ValueError('Document id was not in either the train set nor the test set')
    train_X = X_padded[train_indices]
    train_Y_word = Y_padded_word[train_indices]
    train_Y_sentence = Y_sentence[train_indices]
    train_weights = weights_padded[train_indices]
    val_X = X_padded[val_indices]
    val_Y_word = Y_padded_word[val_indices]
    val_Y_sentence = Y_sentence[val_indices]
    val_weights = weights_padded[val_indices]
    test_X = X_padded[test_indices]
    test_Y_word = Y_padded_word[test_indices]
    test_Y_sentence = Y_sentence[test_indices]
    test_weights = weights_padded[test_indices]
     
    #shuffle
             
    permutation = numpy.random.permutation(train_X.shape[0])
    train_X = train_X[permutation]
    train_Y_word = train_Y_word[permutation]
    train_Y_sentence = train_Y_sentence[permutation]
    train_weights = train_weights[permutation]
    permutation = numpy.random.permutation(val_X.shape[0])
    val_X = val_X[permutation]
    val_Y_word = val_Y_word[permutation]
    val_Y_sentence = val_Y_sentence[permutation]
    val_weights = val_weights[permutation]
    permutation = numpy.random.permutation(test_X.shape[0])
    test_X = test_X[permutation]
    test_Y_word = test_Y_word[permutation]
    test_Y_sentence = test_Y_sentence[permutation]
    test_weights = test_weights[permutation]
     
    # Save preprocessed dataset to file
    grp = outfile.create_group('fold' + str(fold_idx))
    grp.create_dataset('train_X', data=train_X)
    grp.create_dataset('train_Y_word', data=train_Y_word)
    grp.create_dataset('train_Y_sentence', data=train_Y_sentence)
    grp.create_dataset('train_weights', data=train_weights)
    grp.create_dataset('val_X', data=val_X)
    grp.create_dataset('val_Y_word', data=val_Y_word)
    grp.create_dataset('val_Y_sentence', data=val_Y_sentence)
    grp.create_dataset('val_weights', data=val_weights)
    grp.create_dataset('test_X', data=test_X)
    grp.create_dataset('test_Y_word', data=test_Y_word)
    grp.create_dataset('test_Y_sentence', data=test_Y_sentence)
    grp.create_dataset('test_weights', data=test_weights)
outfile.flush()
outfile.close()

print('done')

























