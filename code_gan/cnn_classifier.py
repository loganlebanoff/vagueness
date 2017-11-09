import numpy as np
import tensorflow as tf
import os
import time
import h5py
import param_names
import utils
import load
import acgan_model
import argparse
from sklearn import metrics
import sys
from cnn import cnn

parser = argparse.ArgumentParser()
parser.add_argument("--train", help="run in train mode",
                    action="store_true")
parser.add_argument("--xval", help="perform five-fold cross validation",
                    action="store_true")
parser.add_argument("--generated_dataset", help="use the generated dataset rather than the manually annotated dataset",
                    action="store_true")
args = parser.parse_args()

if args.generated_dataset:
    prediction_words_file = '/predictions_words_cnn_classifier_unsupervised'
    ckpt_dir = '../models/cnn_classifier_unsupervised_ckpts'
else:
    prediction_words_file = '/predictions_words_cnn_classifier'
    ckpt_dir = '../models/cnn_classifier_ckpts'
    
prediction_folder = '../predictions'
summary_file = '/home/logan/tmp'
# train_variables_file = '../models/tf_enc_dec_variables.npz'
use_checkpoint = False
num_folds = 5

start_time = time.time()

FLAGS = tf.app.flags.FLAGS
tf.app.flags.DEFINE_integer('EPOCHS', 50,
                            'Num epochs.')
tf.app.flags.DEFINE_integer('VOCAB_SIZE', 5000,
                            'Number of words in the vocabulary.')
tf.app.flags.DEFINE_integer('LATENT_SIZE', 512,
                            'Size of both the hidden state of RNN and random vector z.')
tf.app.flags.DEFINE_integer('SEQUENCE_LEN', 50,
                            'Max length for each sentence.')
tf.app.flags.DEFINE_integer('EMBEDDING_SIZE', 300,
                            'Max length for each sentence.')
tf.app.flags.DEFINE_integer('PATIENCE', 4,
                            'How many epochs to wait before early stopping.')
tf.app.flags.DEFINE_integer('BATCH_SIZE', 64,
                            'Max length for each sentence.')
tf.app.flags.DEFINE_integer('NUM_CLASSES', 4,
                            'Max length for each sentence.')
tf.app.flags.DEFINE_integer('CLASS_EMBEDDING_SIZE', 1,
                            'Max length for each sentence.')
tf.app.flags.DEFINE_string('CELL_TYPE', 'GRU',
                            'Which RNN cell for the RNNs.')
tf.app.flags.DEFINE_string('MODE', 'TRAIN',
                            'Whether to run in train or test mode.')
tf.app.flags.DEFINE_float('KEEP_PROB', 0.5,
                            'Dropout probability of keeping a node')
tf.app.flags.DEFINE_string("FILTER_SIZES", "3,4,5", 
                            "Comma-separated filter sizes (default: '3,4,5')")
tf.app.flags.DEFINE_integer("NUM_FILTERS", 128, 
                            "Number of filters per filter size (default: 128)")
tf.set_random_seed(123)
np.random.seed(123)
'''
--------------------------------

LOAD DATA

--------------------------------
'''
    
''' Make directories for model files and prediction files ''' 
utils.create_dirs(ckpt_dir, num_folds)
utils.create_dirs(prediction_folder, num_folds)
        
embedding_weights = load.load_embedding_weights()
d, word_to_id = load.load_dictionary()

Metrics = utils.Metrics()
        
'''
--------------------------------

MODEL

--------------------------------
'''
l2_reg_lambda = 0.01

print('building model')
filter_sizes = list(map(int, FLAGS.FILTER_SIZES.split(",")))
num_filters_total = FLAGS.NUM_FILTERS * len(filter_sizes)
keep_prob = tf.placeholder(tf.float32, name='keep_prob')
inputs = tf.placeholder(tf.int32, shape=(None, FLAGS.SEQUENCE_LEN), name='inputs')
targets = tf.placeholder(tf.int32, shape=(None,), name='targets')

embedding_tensor = tf.Variable(initial_value=embedding_weights, name='embedding_matrix')
embeddings = tf.nn.embedding_lookup(embedding_tensor, inputs)
pooled_outputs = cnn(embeddings, keep_prob)

# Final (unnormalized) scores and predictions
with tf.name_scope("output"):
    scores = tf.layers.dense(pooled_outputs, FLAGS.NUM_CLASSES, name='scores')
    predictions = tf.cast(tf.argmax(scores, 1, name="predictions"), tf.int32)

tvars = tf.trainable_variables()
tvar_names = [var.name for var in tvars]
tvars_excluding_filters = [var for var in tvars if 'cnn' in var.name]

# Calculate mean cross-entropy loss
with tf.name_scope("loss"):
    losses = tf.nn.sparse_softmax_cross_entropy_with_logits(labels=targets, logits=scores)
    l2_loss = tf.add_n([ tf.nn.l2_loss(v) for v in tvars_excluding_filters ])
    loss = tf.reduce_mean(losses) + l2_reg_lambda * l2_loss

# Accuracy
with tf.name_scope("accuracy"):
    correct_predictions = tf.equal(predictions, targets)
    accuracy = tf.reduce_mean(tf.cast(correct_predictions, "float"), name="accuracy")


# TODO: change to rms optimizer
optimizer = tf.train.AdamOptimizer().minimize(loss, var_list=tvars)

global_step = tf.Variable(-1, name='global_step', trainable=False)
saver = tf.train.Saver()

for var in tvars:
    utils.variable_summaries(var) 
merged = tf.summary.merge_all()








    
def validate(sess, val_x, val_y):
    def run_val_step(sess, batch_x, batch_y):
        to_return = loss
        return sess.run(to_return,
                    feed_dict={inputs: batch_x,
                               targets: batch_y,
                               keep_prob: 1})
    sum_cost = 0
    for batch_x, batch_y, cur, data_len in utils.batch_generator(val_x, val_y):
        batch_cost = run_val_step(sess, batch_x, batch_y)
        sum_cost += batch_cost * len(batch_y)  # Add up cost based on how many instances in batch
    val_cost = sum_cost / len(val_y)
    return val_cost
    
    
def train(train_x, train_y, val_x, val_y, fold_num):
    
    def run_train_step(sess, batch_x, batch_y):
        to_return = [optimizer, loss, accuracy, merged]
        return sess.run(to_return,
                    feed_dict={inputs: batch_x,
                               targets: batch_y,
                               keep_prob: FLAGS.KEEP_PROB})
        
    
    print 'training'
    with tf.Session() as sess:
        train_writer = tf.summary.FileWriter(summary_file + '/train', sess.graph)
        saver = tf.train.Saver(max_to_keep=5)
        tf.global_variables_initializer().run()
        min_val_cost = np.inf
        num_mistakes = 0
        
        fold_ckpt_dir = ckpt_dir + '/' + str(fold_num)
        variables_file = fold_ckpt_dir + '/tf_acgan_variables_'
        if use_checkpoint:
            ckpt = tf.train.get_checkpoint_state(fold_ckpt_dir)
            if ckpt and ckpt.model_checkpoint_path:
                print ckpt.model_checkpoint_path
                model.saver.restore(sess, ckpt.model_checkpoint_path)  # restore all variables
    
        start = global_step.eval() + 1  # get last global_step and start the next one
        print "Start from:", start
        
        xaxis = 0
        step = 0
        for cur_epoch in range(start, FLAGS.EPOCHS):
            disc_steps = 3
            step_ctr = 0
            for batch_x, batch_y, cur, data_len in utils.batch_generator(train_x, train_y):
                for j in range(1):
                    _, batch_cost, batch_accuracy, summary = run_train_step(sess, batch_x, batch_y)
                    train_writer.add_summary(summary, step)
                    print('Fold', fold_num, 'Epoch: ', cur_epoch,)
                    print('Instance ', cur, ' out of ', data_len)
                    print('Loss: {:.4}'. format(batch_cost))
                    print('Acc: ', batch_accuracy)
                    print()
            
            print 'saving model to file:'
            global_step.assign(cur_epoch).eval()  # set and update(eval) global_step with index, cur_epoch
            saver.save(sess, fold_ckpt_dir + "/model.ckpt", global_step=cur_epoch)
            vars = sess.run(tvars)
            tvar_names = [var.name for var in tf.trainable_variables()]
            variables = dict(zip(tvar_names, vars))
            np.savez(variables_file, **variables)
            
            val_cost = validate(sess, val_x, val_y)
            print('Val Loss: ', val_cost)
            if val_cost < min_val_cost:
                min_val_cost = val_cost
            else:
                num_mistakes += 1
            if num_mistakes >= FLAGS.PATIENCE:
                print 'Stopping early at epoch: ', cur_epoch
                break
            
        
            
        train_writer.close()
            
        
    
def test(test_x, test_y, fold_num):
    
    def run_test_step(sess, batch_x):
        to_return = scores
        return sess.run(to_return,
                        feed_dict={inputs: batch_x,
                               keep_prob: 1})
    def predict(sess, x, y):
        predictions = []
        utils.Progress_Bar.startProgress('testing')
        for batch_x, batch_y, cur, data_len in utils.batch_generator(x, y, batch_size=1):
            batch_predictions = run_test_step(sess, batch_x)
            predictions.append(batch_predictions)
            utils.Progress_Bar.progress(float(cur) / float(data_len) * 100)
        utils.Progress_Bar.endProgress()
        predictions = np.concatenate(predictions)
        predictions_indices = np.argmax(predictions, axis=1)
        f1_score = metrics.f1_score(y, predictions_indices, average='macro')
        return predictions_indices, f1_score
    
    print 'testing'
    with tf.Session() as sess:
        saver = tf.train.Saver(max_to_keep=5)
        tf.global_variables_initializer().run()
        fold_ckpt_dir = ckpt_dir + '/' + str(fold_num)
        ckpt = tf.train.get_checkpoint_state(fold_ckpt_dir)
        if not ckpt:
            raise Exception('Could not find saved model in: ' + fold_ckpt_dir)
        if ckpt and ckpt.model_checkpoint_path:
            print ckpt.model_checkpoint_path
            saver.restore(sess, ckpt.model_checkpoint_path)  # restore all variables
        predictions_indices, _ = predict(sess, test_x, test_y)
        Metrics.print_and_save_metrics(test_y, predictions_indices)
        
def run_on_fold(args, fold_num):
    if args.generated_dataset:
        train_x, train_y, val_x, val_y, test_x, test_y = load.load_generated_data()
    else:
        train_x, train_y, val_x, val_y, test_x, test_y = load.load_annotated_data(fold_num)
#     args.train = True
    
    if args.train:
        train(train_x, train_y, val_x, val_y, fold_num)
    else:
        test(test_x, test_y, fold_num)
    
        
    
def main(unused_argv):
    args.xval = True
    if args.xval:
        metrics_collections = []
        for fold_num in range(num_folds):
            run_on_fold(args, fold_num)
        if not args.train:
            Metrics.print_metrics_for_all_folds()
            
    else:
        run_on_fold(args, 0)

    localtime = time.asctime(time.localtime(time.time()))
    print "Finished at: ", localtime       
    print('Execution time: ', (time.time() - start_time) / 3600., ' hours')
    
if __name__ == '__main__':
  tf.app.run()
    
    
    
    
