#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function
import numpy
import theano
import codecs
import operator
import h5py
import shelve
#testest
from collections import OrderedDict

import gensim
from gensim.models.word2vec import Word2Vec

numpy.random.seed(123)
from keras.preprocessing.text import Tokenizer
from keras.preprocessing.sequence import pad_sequences
from keras.models import Sequential, Model, load_model
from keras.layers import Dense, Dropout, Activation, merge, Input, TimeDistributed
from keras.layers import Embedding, LSTM, GRU
from keras.utils import np_utils
from keras import backend as K
from keras.regularizers import l2

from metrics import performance

train_file = 'Privacy_Sentences.txt'
state_file = 'states.h5'
word_id_file = 'train.h5'
dict_file = 'words.dict'
embedding_file = 'GoogleNews-vectors-negative300.bin'
vague_file = 'vague_terms'
program_state_file = 'program_state'
predict_file = 'predictions.h5'
predict_vague_file = 'predictions_vague.h5'
model_file = 'model_LM_V.h5'
 
fast = False
load_existing_model = False
load_shelf = False
 
vocab_size = 5000
embedding_dim = 300
maxlen = 50
hidden_dim = 512
batch_size = 128
val_samples = batch_size * 10
nb_epoch = 30
samples_per_epoch = None
train_ratio = 0.8
 
if fast:
    nb_epoch = 1
    samples_per_epoch = 100

if not load_shelf:
    # load file, one sentence per line
    sentences = []
    end_tag = ['</s>']
    with codecs.open(train_file) as infile:
        for line in infile:
            words = line.strip().split() + end_tag
            sentences.append(' '.join(words))
    print('total number of sentences in train file: %d' % len(sentences))
        
    # tokenize, create vocabulary
    tokenizer = Tokenizer(nb_words=vocab_size, filters=' ')
    tokenizer.fit_on_texts(sentences)
    word_id_seqs = tokenizer.texts_to_sequences(sentences)
    print('finished creating the dictionary')
        
    # output dictionary
    with codecs.open(dict_file, 'w') as outfile:
        for word, idx in sorted(tokenizer.word_index.items(), key=operator.itemgetter(1)):
            outfile.write('%s %d\n' % (word, idx))
        
    # output list of word ids
    total_word_ids = 0
    my_word_ids = []
    for word_id_seq in word_id_seqs:
        for word_id in word_id_seq[-maxlen-1:]: #TODO
            total_word_ids += 1
            my_word_ids.append(word_id)
        
    outfile = h5py.File(word_id_file, 'w')
    states = outfile.create_dataset('words', data=numpy.array(my_word_ids))
    outfile.flush()
    outfile.close()
        
        
    # load file containing vague terms
    vague_terms = []
    with codecs.open(vague_file) as infile:
        for line in infile:
            words = line.strip().split()
            word_ids = []
            for w in words: 
                word_ids.append(tokenizer.word_index[w] if w in tokenizer.word_index else 0)
            vague_terms.append(word_ids)
        
    # prepare data
    X_raw = []
    Y_raw = []
    Y_vague = []
        
    # calculate statistics
    total_vague_terms = 0
    total_terms = 0
    total_vague_sents = 0
        
    for word_id_seq in word_id_seqs:
        X_raw.append(word_id_seq[:-1])
        Y_raw.append(word_id_seq[1:])
            
        X_curr = word_id_seq[:-1]
        X_curr_len = len(X_curr)
        Y_curr = [0] * X_curr_len
        for idx in xrange(X_curr_len):
            for gap in xrange(1,6):
                if idx + gap > X_curr_len: break
                if X_curr[idx:idx+gap] in vague_terms:
                    Y_curr[idx:idx+gap] = [1] * gap
        Y_vague.append(Y_curr)
            
        vague_flag = 0
        for vv in Y_curr:
            if vv == 1: 
                total_vague_terms += 1
                vague_flag = 1
        total_terms += X_curr_len
        if vague_flag == 1: total_vague_sents += 1
            
            
    print('total vague terms: %d' % (total_vague_terms))
    print('total vague sentences: %d' % (total_vague_sents))
    print('total terms: %d' % (total_terms))
               
    # prepare embedding weights
    word2vec_model = Word2Vec.load_word2vec_format(embedding_file, binary=True)
    embedding_weights = numpy.zeros((vocab_size, embedding_dim), dtype=theano.config.floatX)
       
    n_words_in_word2vec = 0
    n_words_not_in_word2vec = 0
       
    for word, idx in tokenizer.word_index.items():
        if idx < vocab_size:
            try: 
                embedding_weights[idx,:] = word2vec_model[word]
                n_words_in_word2vec += 1
            except:
                embedding_weights[idx,:] = 0.01 * numpy.random.randn(1, embedding_dim).astype(theano.config.floatX)
                n_words_not_in_word2vec += 1
    print('%d words found in word2vec, %d are not' % (n_words_in_word2vec, n_words_not_in_word2vec))
        
        
        
    my_shelf = shelve.open(program_state_file,'n') # 'n' for new
    for key in dir():
        try:
            if key == 'word2vec_model':
                continue
            my_shelf[key] = globals()[key]
        except TypeError:
            #
            # __builtins__, my_shelf, and imported modules can not be shelved.
            #
            print('ERROR shelving: {0}'.format(key))
    my_shelf.close()
    print('done shelving')

else:
    # load program state
    my_shelf = shelve.open(program_state_file)
    for key in my_shelf:
        globals()[key]=my_shelf[key]
    my_shelf.close()
    print('done loading shelve')

X_padded = pad_sequences(X_raw, maxlen=maxlen)
Y_padded = pad_sequences(Y_raw, maxlen=maxlen)
Y_padded_vague = pad_sequences(Y_vague, maxlen=maxlen)
Y_padded_vague = Y_padded_vague.reshape(Y_padded_vague.shape[0], Y_padded_vague.shape[1], 1)

# split train and test
permutation = numpy.random.permutation(X_padded.shape[0])
X_padded = X_padded[permutation]
Y_padded = Y_padded[permutation]
Y_padded_vague = Y_padded_vague[permutation]
train_len = int(len(X_padded) * train_ratio)
train_X_padded = X_padded[:train_len]
train_Y_padded = Y_padded[:train_len]
train_Y_padded_vague = Y_padded_vague[:train_len]
test_X_padded = X_padded[train_len:]
test_Y_padded = Y_padded[train_len:]
test_Y_padded_vague = Y_padded_vague[train_len:]
if not samples_per_epoch:
    samples_per_epoch = train_X_padded.shape[0]
    
# truncate because of keras's predict generator bug
len_test = test_X_padded.shape[0] - (test_X_padded.shape[0] % val_samples)
test_X_padded = test_X_padded[:len_test]
test_Y_padded = test_Y_padded[:len_test]
test_Y_padded_vague = test_Y_padded_vague[:len_test]

# data generatorc
def batch_generator(X_padded, Y_padded, Y_padded_vague, batch_size):
    number_of_batches = samples_per_epoch/batch_size
    counter=0
    
    shuffle_index = numpy.arange(Y_padded.shape[0])
    numpy.random.shuffle(shuffle_index)
        
    while True:
        index_batch = shuffle_index[batch_size*counter:batch_size*(counter+1)]
        
        X_batch = X_padded[index_batch]
        Y_batch = Y_padded[index_batch]
        Y_batch_vague = Y_padded_vague[index_batch]
        
        Y_batch_categorical = numpy.array(np_utils.to_categorical(Y_batch.flatten(), vocab_size))
        Y_batch_categorical = Y_batch_categorical.reshape(Y_batch.shape[0], Y_batch.shape[1], vocab_size)
        
        counter += 1
        if counter == number_of_batches:
            numpy.random.shuffle(shuffle_index)
            counter = 0

        yield (X_batch, [Y_batch_categorical, Y_batch_vague])
        
if not load_existing_model:
    # build model
    my_input = Input(shape=(maxlen,), dtype='int32')
    
    embedded = Embedding(vocab_size, 
                  embedding_dim, 
                  input_length=maxlen, 
                  weights=[embedding_weights], 
                  dropout=0.2,
                  trainable=False)(my_input)
                  
    forwards = GRU(hidden_dim,
                   return_sequences=True,
                   dropout_W=0.2,
                   dropout_U=0.2)(embedded)
    
    output = Dropout(0.5)(forwards)
    
    output_lm = TimeDistributed(Dense(vocab_size, activation='softmax'), name='loss_lm')(output)
    output_vague = TimeDistributed(Dense(1, activation='sigmoid'), name='loss_vague')(output)
    
    # forwards = GRU(hidden_dim,
    #                return_sequences=True,
    #                dropout_W=0.2,
    #                dropout_U=0.2,
    #                W_regularizer=l2(0.1),
    #                U_regularizer=l2(0.1),
    #                b_regularizer=l2(0.1))(embedded)
    # 
    # output = Dropout(0.5)(forwards)
    # 
    # output_lm = TimeDistributed(Dense(vocab_size, activation='softmax', W_regularizer=l2(0.1), b_regularizer=l2(0.1)), name='loss_lm')(output)
    # output_vague = TimeDistributed(Dense(1, activation='sigmoid', W_regularizer=l2(0.1), b_regularizer=l2(0.1)), name='loss_vague')(output)
    
    model = Model(input=my_input, output=[output_lm, output_vague])
    model.compile(optimizer='rmsprop',
                  loss={'loss_lm':'categorical_crossentropy',
                        'loss_vague':'binary_crossentropy'},
                  loss_weights={'loss_lm': 1.,
                                'loss_vague': 1.},
                  metrics=['accuracy'])
    
    get_hidden_layer = K.function([model.layers[0].input, K.learning_phase()],
                                      [model.layers[2].output])
    
    model.fit_generator(batch_generator(train_X_padded, train_Y_padded, train_Y_padded_vague, batch_size), 
                        samples_per_epoch=samples_per_epoch, nb_epoch=nb_epoch)
    model.save(model_file)
else:
    model = load_model(model_file)

#test
outfile = h5py.File(predict_file, 'w')
Y_predict = outfile.create_dataset('Y_predict', (test_X_padded.shape[0], test_X_padded.shape[1], vocab_size))
Y_vague_predict = outfile.create_dataset('Y_predict_vague', (test_X_padded.shape[0], test_X_padded.shape[1], 1))
idx = 0
while idx < test_X_padded.shape[0] - (test_X_padded.shape[0] % val_samples):
# for i in range(2):
    print('Test: ' + str(idx) + '/' + str(test_X_padded.shape[0]))
    end = min(idx + val_samples, test_X_padded.shape[0])
    Y_predict[idx:end], Y_vague_predict[idx:end] = model.predict_generator(
    batch_generator(test_X_padded, test_Y_padded, test_Y_padded_vague, batch_size), 
    val_samples)
    idx += val_samples
Y_vague_predict = numpy.round(Y_vague_predict)
accuracy, precision, recall, f1score = performance(Y_vague_predict, test_Y_padded_vague)
print('Accuracy:\t' + str(accuracy))
print('Precision:\t' + str(precision))
print('Recall:\t' + str(recall))
print('F1 score:\t' + str(f1score))
outfile.flush()
outfile.close()

# # save hidden state representations to file
# outfile = h5py.File(state_file, 'w')
# states = outfile.create_dataset('output1', (total_word_ids, hidden_dim))
# 
# pos = 0
# for kk in xrange(len(X_raw)):
# #     print(kk)
#     layer_output = get_hidden_layer([X_padded[kk:kk+1], 0])[0]
#     layer_output = layer_output.reshape(layer_output.shape[1], layer_output.shape[2])
#     sent_len = maxlen if len(X_raw[kk]) > maxlen else len(X_raw[kk])
#     states[pos:pos+sent_len] = layer_output[-sent_len:]
#     states[pos+sent_len] = numpy.zeros(hidden_dim)
#     pos += sent_len + 1
# 
# outfile.flush()
# outfile.close()
print('done')

















































